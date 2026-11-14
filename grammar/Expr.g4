
grammar Expr;

@parser::members {
def _block_like(self, ctx):
	if ctx.stop.type == self.T__12: return True # LBRACE
	la = self._input.LA(1)
	return la == Token.EOF or la == self.T__12
}

program: (e=expr (';' | {self._block_like($e.ctx)}?))* EOF;

expr: '(' expr ')' # Paren
	| expr '(' (expr (',' expr)*)? ')' # Call
	| expr '[' expr ']' # Index
	| expr '.' ID # Attr
	| op=('+' | '-' | '~' | '!') expr # Unary
	| expr '{' (arm (',' arm)*) '}' # Match
	| expr op=('*' | '/') expr # Binary
	| expr op=('<<' | '>>') expr # Binary
	| expr op=('+' | '-') expr # Binary
	| expr op=('&' | '|' | '^') expr # Binary
	| expr op='&&' expr # Binary
	| expr op='||' expr # Binary
	| <assoc=right> expr op=('+=' | '-=' | '*=' | '/=' | '&=' | '|=' | '^=' | '&&=' | '||=' | '<<=' | '>>=') expr # InPlace
	| expr op=('<' | '>' | '==' | '<=' | '>=') expr # Binary
	| <assoc=right> expr '?' expr ':' expr # Ternary
	| <assoc=right> expr '::' expr # While
	| <assoc=right> ID ':=' expr # Create
	| <assoc=right> expr '=' expr # Assign
	| 'use' ID ('.' ID)* # Use
	| 'use' ID ('.' ID)* 'as' ID # UseWithBind
	| 'break' expr? # Break
	| 'continue' # Continue
	| 'return' expr? # Return
	| atom # Single
	;

atom: <assoc=right> ID '(' (ID (',' ID)*)? ')' '=>' expr # NamedFn
	| <assoc=right> '(' (ID (',' ID)*)? ')' '=>' expr # AnonyFn
	| ID # Id
	| FLOAT # Float
	| INT # Int
	| STRING # String
	| '[' (expr (',' expr )*)? ']' # Array
	| '{' (e=expr (';' | {self._block_like($e.ctx)}?))* '}' # Block
	| '{' (entry (',' entry )*)? ','? '}' # Map
	;

arm: atom '->' expr;
entry: atom ':' expr;

INT: [0-9]+;
FLOAT: [0-9]+ '.' [0-9]+;
STRING: '"' .*? '"';
ID: [a-zA-Z_][a-zA-Z0-9_]*;

WS: [ \t\r\n]+ -> skip;
COM: ('//' ~[\n]* | '/*' .*? '*/') -> skip;
