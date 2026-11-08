
grammar Expr;

program: expr* EOF;

expr: '(' expr ')' # Paren
	| expr '(' (expr (',' expr)*)? ')' # Call
	| ('+' | '-') expr # Unary
	| expr op=('*' | '/') expr # Binary
	| expr op=('+' | '-') expr # Binary
	| <assoc=right> ID ':=' expr # Create
	| <assoc=right> lvalue '=' expr # Assign
	| lvalue # Read
	| atom # Single
	;

atom: FLOAT # Float
	| INT # Int
	| STRNG # String
	;

lvalue: ID # LVar
	| lvalue '[' expr ']' # LIndex
	| lvalue '.' ID # LPropr
	;

INT: [0-9]+;
FLOAT: [0-9]+ '.' [0-9]+;
STRNG: '"' .*? '"';
ID: [a-zA-Z_][a-zA-Z0-9_]*;

WS: [ \t\n\r]+ -> skip;
COM: ('//' ~[\n]* | '/*' .*? '*/') -> skip;
