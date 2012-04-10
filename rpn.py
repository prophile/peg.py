import peg, string
from collections import namedtuple

AddExpr = namedtuple('AddExpr', 'lhs rhs')
SubExpr = namedtuple('SubExpr', 'lhs rhs')
MulExpr = namedtuple('MulExpr', 'lhs rhs')
DivExpr = namedtuple('DivExpr', 'lhs rhs')
PowExpr = namedtuple('PowExpr', 'lhs rhs')
VarExpr = namedtuple('VarExpr', 'name')

class AlgebraicParser(peg.Parser):
    @peg.complete
    def expression(self):
        return self.additive()

    @peg.memoised
    def additive(self):
        operators = {'+': AddExpr,
                     '-': SubExpr}
        return self.operator_reduce(self.multiplicative,
                                    operators)

    @peg.memoised
    def multiplicative(self):
        operators = {'*': MulExpr,
                     '/': DivExpr}
        return self.operator_reduce(self.exponential,
                                    operators)

    @peg.memoised
    def exponential(self):
        operators = {'^': PowExpr}
        return self.operator_reduce(self.base,
                                    operators,
                                    associativity = "right")

    def parens(self):
        return self.surrounded('()', self.additive)

    def variable(self):
        return VarExpr(name = self.span(string.ascii_letters))

    def base(self):
        return self.choose(self.parens,
                           self.variable)

evaluate_algebraic = peg.Evaluator()

@peg.evaluates(evaluate_algebraic, AddExpr)
def add_eval(lhs, rhs):
    return (evaluate_algebraic(lhs) +
            evaluate_algebraic(rhs) +
            ['+'])

@peg.evaluates(evaluate_algebraic, SubExpr)
def sub_eval(lhs, rhs):
    return (evaluate_algebraic(lhs) +
            evaluate_algebraic(rhs) +
            ['-'])

@peg.evaluates(evaluate_algebraic, MulExpr)
def mul_eval(lhs, rhs):
    return (evaluate_algebraic(lhs) +
            evaluate_algebraic(rhs) +
            ['*'])

@peg.evaluates(evaluate_algebraic, DivExpr)
def div_eval(lhs, rhs):
    return (evaluate_algebraic(lhs) +
            evaluate_algebraic(rhs) +
            ['/'])

@peg.evaluates(evaluate_algebraic, PowExpr)
def pow_eval(lhs, rhs):
    return (evaluate_algebraic(lhs) +
            evaluate_algebraic(rhs) +
            ['^'])

@peg.evaluates(evaluate_algebraic, VarExpr)
def var_eval(name):
    return [name]

def infix_to_rpn(expr):
    parser = AlgebraicParser(expr)
    ast = parser.expression()
    return ''.join(evaluate_algebraic(ast))

import sys
print infix_to_rpn(sys.argv[1])

