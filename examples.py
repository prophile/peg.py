from peg import *

class JSONParser(Parser):
    @complete
    def json(self):
        return self.element()

    def element(self):
        return self.choose(self.object,
                           self.array,
                           self.string,
                           self.json_literal,
                           self.number)

    @memoised
    def object(self):
        def object_member():
            key = self.string()
            self.literal(':')
            value = self.element()
            return (key, value)
        self.literal('{')
        values = self.list(object_member, permit_empty=True)
        self.literal('}')
        return dict(values)

    @memoised
    def array(self):
        self.literal('[')
        values = self.list(self.element, permit_empty=True)
        self.literal(']')
        return values

    @memoised
    def string(self):
        def string_character():
            self.unless_accept('\\"' + ''.join(chr(x) for x in range(0, 32)))
            return self.any()
        def escape():
            self.accept('\\')
            escape_handlers = {'"': lambda: '"',
                               '/': lambda: '/',
                               '\\': lambda: '\\',
                               'b': lambda: '\b',
                               'f': lambda: '\f',
                               'n': lambda: '\n',
                               'r': lambda: '\r',
                               't': lambda: '\t',
                               'u': lambda: self.span(string.hexdigits,
                                                      min=4, max=4)}
            return escape_handlers[self.accept(escape_handlers)]
        def string_element():
            return self.choose(string_character,
                               escape)
        self.accept('"')
        value = self.repeat(string_element,
                            min=0,
                            fold=operator.add,
                            default='')
        self.accept('"')
        self.whitespace()
        return value

    def json_literal(self):
        values = {'true': True,
                  'false': False,
                  'null': None}
        return values[self.word(values)]

    def keywords(self):
        return ('true', 'false', 'null')

AddExpr = namedtuple('AddExpr', 'lhs,rhs')
SubExpr = namedtuple('SubExpr', 'lhs,rhs')
MulExpr = namedtuple('MulExpr', 'lhs,rhs')
DivExpr = namedtuple('DivExpr', 'lhs,rhs')
LiteralExpr = namedtuple('LiteralExpr', 'val')

class ArithmeticParser(Parser):
    @complete
    def start(self):
        return self.additive()

    @memoised
    def additive(self):
        operators = {'+': AddExpr,
                     '-': SubExpr}
        return self.operator_reduce(self.multiplicative,
                                    operators)

    @memoised
    def multiplicative(self):
        operators = {'*': MulExpr,
                     '/': DivExpr}
        return self.operator_reduce(self.primary,
                                    operators)

    def primary(self):
        def paren_expr():
            self.literal('(')
            subexpr = self.additive()
            self.literal(')')
            return subexpr
        return self.choose(self.integer,
                           paren_expr)

    @ast(LiteralExpr)
    def integer(self):
        val = super(ArithmeticParser, self).integer(allow_hex = False)
        return locals()

evaluate_arithmetic = Evaluator()

@evaluates(evaluate_arithmetic, AddExpr)
def add(lhs, rhs):
    return evaluate_arithmetic(lhs) + evaluate_arithmetic(rhs)

@evaluates(evaluate_arithmetic, SubExpr)
def sub(lhs, rhs):
    return evaluate_arithmetic(lhs) - evaluate_arithmetic(rhs)

@evaluates(evaluate_arithmetic, MulExpr)
def mul(lhs, rhs):
    return evaluate_arithmetic(lhs) * evaluate_arithmetic(rhs)

@evaluates(evaluate_arithmetic, DivExpr)
def div(lhs, rhs):
    return evaluate_arithmetic(lhs) / evaluate_arithmetic(rhs)

@evaluates(evaluate_arithmetic, LiteralExpr)
def lit(val):
    return val

