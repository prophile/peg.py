import functools
import string
import operator
from collections import namedtuple

class NoMatchException(Exception):
    pass

class _PositionSaver(object):
    def __init__(self, parser):
        self.parser = parser
        self.stack = []

    def __enter__(self):
        self.stack.append(self.parser.position)
        position = len(self.stack) - 1
        def accept_this_element():
            self.stack[position] = None
        return accept_this_element

    def __exit__(self, type, value, traceback):
        old_value = self.stack.pop()
        if old_value is not None:
            self.parser.position = old_value

def memoised(fn):
    result_undefined = object()
    result_match_error = object()
    @functools.wraps(fn)
    def wrapper(self, *args):
        memoised_key = (self.position, fn, args)
        memoised_value = self._memoised_results.get(memoised_key,
                                                    result_undefined)
        if memoised_value is result_undefined:
            try:
                new_value = fn(self, *args)
                self._memoised_results[memoised_key] = (new_value, self.position)
                return new_value
            except NoMatchException:
                self._memoised_results[memoised_key] = result_match_error
                self.fail()
        elif memoised_value is result_match_error:
            self.fail()
        else:
            saved_value, self.position = memoised_value
            return saved_value
    return wrapper

def eat_whitespace(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        value = fn(self, *args, **kwargs)
        self.whitespace()
        return value
    return wrapper

def unfollowed(chars):
    def wrap(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            value = fn(self, *args, **kwargs)
            self.unless_accept(chars)
            return value
        return wrapper
    return wrap

def complete(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self.saved_position as accept:
            self.whitespace()
            value = fn(self, *args, **kwargs)
            self.whitespace()
            self.eof()
            accept()
            return value
    return wrapper

def predicate(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self.saved_position:
            if not fn(self, *args, **kwargs):
                self.fail()
    return wrapper

def not_predicate(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self.saved_position:
            if fn(self, *args, **kwargs):
                self.fail()
    return wrapper

def ast(tuple_type):
    fields = tuple_type._fields
    def wrap(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            results = fn(self, *args, **kwargs)
            values = dict((field, results[field]) for field in fields)
            return tuple_type(**values)
        return wrapper
    return wrap

def debug(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        result = fn(self, *args, **kwargs)
        print fn.__name__, result
        return result
    return wrapper

class Parser(object):
    def __init__(self, source):
        self.source = source
        self.position = 0
        self.saved_position = _PositionSaver(self)
        self._memoised_results = {}
        self.keyword_alphabet = string.ascii_letters + string.digits + '_'

    def fail(self):
        raise NoMatchException

    def at_eof(self):
        return self.position == len(self.source)

    def accept(self, chars):
        if self.at_eof():
            self.fail()
        char = self.source[self.position]
        if char in chars:
            self.position += 1
            return char
        else:
            self.fail()

    def any(self, count=1):
        if self.position + count < len(self.source):
            # this is the only condition for acceptance
            returned_value = self.source[self.position:self.position+count]
            self.position += count
            return returned_value
        else:
            self.fail()

    def literal(self, string, whitespace=True, charset=None):
        for element in string:
            self.accept(element)
        if charset is not None:
            self.unless_accept(charset)
        if whitespace:
            self.whitespace()

    def word(self, expect, whitespace=True, charset=None):
        keywords = self.keywords()
        if type(expect) == 'str':
            expect = (str,)
        if charset == None:
            charset = self.keyword_alphabet
        value = self.span(charset)
        if whitespace:
            self.whitespace()
        actual_type = value if value in keywords else None
        if actual_type in expect:
            return value
        else:
            self.fail()

    def optional(self, pattern, default=None):
        with self.saved_position as accept:
            try:
                value = pattern()
                accept()
                return value
            except NoMatchException:
                return default

    def repeat(self,
               pattern,
               min=1,
               max=None,
               fold=lambda x, y: x + [y],
               default=[]):
        with self.saved_position as accept_outer:
            current_value = default
            matched_values = 0
            if max == None:
                max = float('inf')
            try:
                while matched_values < max:
                    with self.saved_position as accept_inner:
                        new_value = pattern()
                        matched_values += 1
                        current_value = fold(current_value, new_value)
                        accept_inner()
            except NoMatchException:
                pass # we're just waiting for one of these
            if matched_values < min:
                self.fail()
            accept_outer()
            return current_value

    def _operator_reduce_left(self,
                              higher,
                              operator):
        first = higher()
        def reducer(lhs, next):
            op, rhs = next
            return op(lhs, rhs)
        def single():
            return operator(), higher()
        return self.repeat(single, min=0, fold=reducer, default=first)

    def _operator_reduce_right(self,
                               higher,
                               operator):
        def expr():
            return self.choose(expanded_form,
                               higher)
        def expanded_form():
            left = higher()
            op = operator()
            right = expr()
            return op(left, right)
        return expr()

    def _operator_reduce_none(self,
                              higher,
                              operator):
        left = higher()
        try:
            op = operator()
            right = higher()
            return op(left, right)
        except NoMatchException:
            return left

    def _operator_reduce_nary(self,
                              higher,
                              operator):
        left = higher()
        def suffix():
            op = operator()
            right = higher()
            return op, right
        try:
            suffixes = self.repeat(suffix)
            return suffixes[0][0](*([left] + [s[1] for s in suffixes]))
        except NoMatchException:
            return left

    def operator_reduce(self,
                        higher,
                        operators,
                        whitespace=True,
                        associativity="left"):
        def operator():
            val = operators[self.accept(operators)]
            if whitespace:
                self.whitespace()
            return val
        subhandlers = dict(left = self._operator_reduce_left,
                           right = self._operator_reduce_right,
                           none = self._operator_reduce_none,
                           nary = self._operator_reduce_nary)
        return subhandlers[associativity](higher, operator)

    def list(self,
             element,
             separator=",",
             permit_empty=False):
        if type(separator) == str:
            separator = functools.partial(self.literal, separator)
        with self.saved_position as accept:
            try:
                elements = [element()]
            except NoMatchException:
                if permit_empty:
                    return []
                else:
                    self.fail()
            try:
                while True:
                    with self.saved_position as accept_inner:
                        separator()
                        elements.append(element())
                        accept_inner()
            except NoMatchException:
                pass
            accept()
            return elements

    def choose(self, *options):
        for option in options:
            with self.saved_position as accept:
                try:
                    value = option()
                    accept()
                    return value
                except NoMatchException:
                    pass # continue to the next
        self.fail() # no options matched

    def span(self, chars, min=1, max=None):
        return self.repeat(lambda: self.accept(chars),
                           min=min,
                           max=max,
                           fold=operator.add,
                           default="")

    @predicate
    def eof(self):
        return self.at_eof()

    def when(self, pattern):
        with self.saved_position:
            pattern()

    def unless(self, pattern):
        with self.saved_position:
            try:
                pattern()
            except NoMatchException:
                pass # this is what we want, just let it through
            else:
                self.fail() # it matched

    def unless_accept(self, chars):
        return self.unless(functools.partial(self.accept, chars))

    def surrounded(self, surroundings, subexpression):
        self.literal(surroundings[0])
        val = subexpression()
        self.literal(surroundings[1])
        return val

    def whitespace(self):
        def whitespace_atom():
            try:
                self.span(string.whitespace)
            except NoMatchException:
                if hasattr(self, 'comment'):
                    self.comment()
                else:
                    raise NoMatchException
        self.repeat(whitespace_atom, min = 0)

    def _hex_integer(self):
        self.literal('0x', whitespace=False)
        return int(self.span(string.hexdigits), 16)

    def _oct_integer(self):
        self.accept('0')
        return int(self.span(string.octdigits), 8)

    def _dec_integer(self):
        return int(self.span(string.digits), 10)

    def integer(self,
                whitespace=True,
                allow_hex=True,
                allow_oct=False,
                allow_negative=True):
        def sign():
            signs = {'-': -1, '+': 1}
            return signs[self.accept(signs)]
        def value():
            choices = []
            if allow_hex:
                choices.append(self._hex_integer)
            if allow_oct:
                choices.append(self._oct_integer)
            choices.append(self._dec_integer)
            return self.choose(*choices)
        s = self.optional(sign, default=1) if allow_negative else 1
        v = value()
        if whitespace:
            self.whitespace()
        return s * v

    def float(self,
              whitespace=True):
        def exponent_part():
            self.accept('eE')
            return self.integer(whitespace=False,
                                allow_hex=False)
        whole_part = self.integer(whitespace=False,
                                  allow_hex=False)
        self.accept('.')
        fract_part = self.span(string.digits, min=0)
        exp_part = self.optional(exponent_part)
        if whitespace:
            self.whitespace()
        stringified_value = '{0}.{1}e{2}'.format(whole_part, fract_part, exp_part)
        return float(stringified_value)

    def number(self,
               whitespace=True,
               allow_hex=False,
               allow_oct=False):
        return self.choose(lambda: self.integer(whitespace=whitespace,
                                                allow_hex=allow_hex,
                                                allow_oct=allow_oct),
                           lambda: self.float(whitespace=whitespace))

class Evaluator:
    def __init__(self):
        self.rules = {}

    def __call__(self, node):
        return self.rules[type(node)](**node._asdict())

def evaluates(evaluator, ty):
    def wrapper(fn):
        evaluator.rules[ty] = fn
        return fn
    return wrapper

