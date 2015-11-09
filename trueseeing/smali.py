import re
import collections
import itertools

import pprint
import traceback

class Package:
  def __init__(self, apk):
    self.apk = apk

  def disassembled(self):
    return PackageAnalysis(PackageContent(self.apk).unpacked()).analyzed()

class PackageAnalysis:
  res = None
  smali = None
  unknown = None
  lib = None

  def __init__(self, path):
    self.path = path

  def analyzed(self):
    self.res = []
    self.smali = []
    self.unknown = []
    self.lib = []

class PackageContent:
  def __init__(self, apk):
    self.apk = apk

  def unpacked(self):
    return '/tmp/package/unpacked'

class Directory:
  def __init__(self, path):
    self.path = path

  def remove(self):
    os.path.rmtree(self.path)

  def __enter__(self):
    return self

  def __exit__(self, exc_code, exc_value, traceback):
    self.remove()

class Smali:
  @staticmethod
  def parsed(source_code_in_smali):
    return P.parsed(source_code_in_smali)

class Token:
  t = None
  v = None

  def __init__(self, t, v):
    self.t = t
    self.v = v

  def __repr__(self):
    return '<Token %s:%s>' % (self.t, self.v)

class Program(collections.UserList):
  pass

class Op(Token):
  p = None

  def __init__(self, t, v, p):
    super().__init__(t, v)
    self.p = p

  def __repr__(self):
    return '<Op %s:%s:%s>' % (self.t, self.v, self.p)

class CodeFlows:
  @staticmethod
  def callers_of(method):
    try:
      return (r for r in itertools.chain(*(c.ops for c in method.class_.global_.classes)) if r.t == 'id' and 'invoke' in r.v and method.matches(r.p[1]))
    except:
      return []

  @staticmethod
  def callstacks_of(method):
    o = dict()
    for m in CodeFlows.callers_of(method):
      o[m] = CodeFlows.callstacks_of(m)
    return o

  @staticmethod
  def method_of(op, ops):
    for o in reversed(ops):
      pass

  @staticmethod
  def invocations_in(ops):
    return (o for o in ops if o.t == 'id' and 'invoke' in o.v)

class InvocationPattern:
  def __init__(self, insn, value, i=None):
    self.insn = insn
    self.value = value
    self.i = i

class OpMatcher:
  def __init__(self, ops, *pats):
    self.ops = ops
    self.pats = pats

  def matching(self):
    table = [(re.compile(p.insn), (re.compile(p.value) if p.value is not None else None)) for p in self.pats]
    for o in (o for o in self.ops if o.t == 'id'):
      try:
        if any(ipat.match(o.v) and (vpat is None or vpat.match(o.p[1].v)) for ipat, vpat in table):
          yield o
      except (IndexError, AttributeError):
        pass
      
class DataFlows:
  class RegisterDecodeError(Exception):
    pass
  
  @staticmethod
  def into(o):
    def just(v):
      assert len(v) == 1, 'checkpoint: %r' % v
      if isinstance(v, list):
        return v[0]
      else:
        return tuple(v)[0]
    
    def flattened(d):
      regs = {}
      try:
        for regset in (v.get('load') for v in d['access']):
          r = just(regset)
          assert r not in regs
          regs[r] = [flattened(v) for v in d['access'] if r in v.get('load', frozenset())]
      except (KeyError, AttributeError):
        regs = {}
      if regs:
        return {d['on']:regs}
      else:
        return d['on']
    
    graphs = [flattened(DataFlows.analyze_op(o))]
    return graphs

  @staticmethod
  def decoded_registers_of(ref, type_=set):
    if ref.t == 'multireg':
      regs = ref.v
      if ' .. ' in regs:
        from_, to_ = reg.split(' .. ')
        return type_(['%s%d' % (from_[0], c) for c in range(int(from_[1]), int(to_[1]) + 1)])
      elif ',' in regs:
        return type_([r.strip() for r in regs.split(',')])
      else:
        return type_([regs.strip()])
    elif ref.t == 'reg':
      regs = ref.v
      return type_([regs.strip()])
    else:
      raise DataFlows.RegisterDecodeError("unknown type of reference: %s, %s", ref.t, ref.v)

  @staticmethod
  def analyze_op(op):
    if op.t == 'id':
      if any(op.v.startswith(x) for x in ['const','new-']):
        return dict(on=op, load=DataFlows.decoded_registers_of(op.p[0]))
      elif op.v == 'move-exception':
        return dict(on=op, load=DataFlows.decoded_registers_of(op.p[0]))
      elif op.v == 'move':
        return dict(on=op, load=DataFlows.decoded_registers_of(op.p[0]), access=DataFlows.decoded_registers_of(op.p[1]))
      elif op.v.startswith('invoke'):
        try:
          d = dict(on=op, access=DataFlows.analyze_load(op, DataFlows.decoded_registers_of(op.p[0])))
          if op.v.endswith('-virtual') or op.v.endswith('-direct'):
            d.update(dict(subject=DataFlows.analyze_subject(op, DataFlows.decoded_registers_of(op.p[0], type_=list)[0])))
          return d
        except DataFlows.RegisterDecodeError:
          return dict()
      elif op.v.startswith('move-result'):
        return DataFlows.analyze_ret(op)
      else:
        try:
          return dict(on=op, access=DataFlows.decoded_registers_of(op.p[0]))
        except DataFlows.RegisterDecodeError:
          return dict()

  @staticmethod
  def analyze_ret(from_):
    for o in reversed(from_.method_.ops[:from_.method_.ops.index(from_)]):
      if o.t == 'id' and o.v.startswith('invoke'):
        try:
          return dict(on=o, load=DataFlows.decoded_registers_of(from_.p[0]), access=DataFlows.analyze_op(o)['access'])
        except KeyError:
          return dict(on=o, load=DataFlows.decoded_registers_of(from_.p[0]))          

        
  # XXX: assuming that a) the subject lifecycle could conclude in the function, and b) the subject register holds during the function.
  @staticmethod
  def analyze_subject(from_, subject):
    reg = []
    for o in reversed(from_.method_.ops[:from_.method_.ops.index(from_)]):
      if o.t == 'id':
        access = DataFlows.decoded_registers_of(o.p[0], type_=list)
        if subject == access[0]:
          if o.v.startswith('invoke'):
            reg.append(o)
          elif any(o.v.startswith(x) for x in ['const', 'new-', 'move']):
            break
    return [DataFlows.analyze_op(o) for o in reg]

  @staticmethod
  def analyze_load(from_, regs):
    ret = []
    unsolved = set(regs)
    for o in reversed(from_.method_.ops[:from_.method_.ops.index(from_)]):
      if unsolved:
        d = DataFlows.analyze_op(o)
        if d is not None:
          try:
            if d['load'] & unsolved:
              ret.append(d)
              unsolved = unsolved - d['load']
          except KeyError:
            pass
    return ret

class Class(Op):
  def __init__(self, p, methods, fields):
    super().__init__('class', [t for t in p if t.t == 'reflike'][0], None)
    self.attrs = set([t for t in p if t.t == 'id'])
    self.methods = methods if methods else []
    self.fields = fields if fields else []
    self.super_ = None
    self.source = None
    self.global_ = None
    self.ops = Program()

  def __repr__(self):
    return '<Class %s:%s, attrs:%s, super:%s, source:%s, methods:[%d methods], fields:[%d fields], ops:[%d ops]>' % (self.t, self.v, self.attrs, self.super_, self.source, len(self.methods), len(self.fields), len(self.ops))

  def qualified_name(self):
    return self.v.v

class App:
  classes = []

class Annotation(Op):
  name = None
  content = None

  def __init__(self, v, p, content):
    super().__init__('annotation', v, p)
    self.content = content

  def __repr__(self):
    return '<Annotation %s:%s:%s, content:%s>' % (self.t, self.v, self.p, self.content)

class Method(Op):
  attrs = None
  ops = Program()

  def __init__(self, p, ops):
    super().__init__('method', Token('prototype', ''.join((t.v for t in p[-2:]))), p)
    self.attrs = set(p[:-2])
    self.ops = ops

  def __repr__(self):
    return '<Method %s:%s, attrs:%s, ops:[%d ops]>' % (self.t, self.v, self.attrs, len(self.ops))

  def matches(self, reflike):
    return self.qualified_name() in reflike.v

  def qualified_name(self):
    return '%s->%s' % (self.class_.qualified_name(), self.v.v)

class P:
  @staticmethod
  def head_and_tail(xs):
    try:
      return xs[0], xs[1:]
    except IndexError:
      return xs[0], None

  @staticmethod
  def parsed(s):
    app = App()
    class_ = None
    method_ = None

    for t in (r for r in P.parsed_flat(s)):
      if t.t == 'directive' and t.v == 'class':
        class_ = Class(t.p, [], [])
        class_.global_ = app
        app.classes.append(class_)
      else:
        assert class_ is not None
        t.class_ = class_
        class_.ops.append(t)
        if method_ is None:
          if t.t == 'directive':
            if t.v == 'super':
              class_.super_ = t.p[0]
            elif t.v == 'source':
              class_.source = t.p[0]
            elif t.v == 'method':
              method_ = Method(t.p, [])
              method_.class_ = class_
            else:
              pass
        else:
          t.method_ = method_
          if isinstance(t, Annotation):
            method_.p.append(t)
          else:
            if t.t == 'directive' and t.v == 'end' and t.p[0].v == 'method':
              class_.methods.append(method_)
              method_ = None
            else:
              method_.ops.append(t)

    return class_

  @staticmethod
  def parsed_flat(s):
    q = collections.deque(re.split(r'\n+', s))
    while q:
      l = q.popleft()
      if l:
        t = P.parsed_as_op(l)
        if t.t == 'directive' and t.v == 'annotation':
          yield Annotation(t.v, t.p, P.parsed_as_annotation_content(q))
        else:
          yield t

  @staticmethod
  def parsed_as_op(l):
    x, xs = P.head_and_tail([t for t in P.lexed_as_smali(l)])
    return Op(x.t, x.v, xs)

  @staticmethod
  def parsed_as_annotation_content(q):
    content = []
    try:
      while '.end annotation' not in q[0]:
        content.append(q.popleft())
    except IndexError:
      pass
    return content

  @staticmethod
  def lexed_as_smali(l):
    for m in re.finditer(r':(?P<label>[a-z0-9_-]+)|{\s*(?P<multilabel>(?::[a-z0-9_-]+(?: .. )*)+\s*)}|\.(?P<directive>[a-z0-9_-]+)|"(?P<string>.*)"|(?P<reg>[vp][0-9]+)|{(?P<multireg>[vp0-9,. ]+)}|(?P<id>[a-z0-9/-]+)|(?P<reflike>[A-Za-z_0-9/;$()<>-]+)|#(?P<comment>.*)', l):
      key = m.lastgroup
      value = m.group(key)
      yield Token(key, value)

if __name__ == '__main__':
    Package(apk).disassembled().of('filename.smali')
