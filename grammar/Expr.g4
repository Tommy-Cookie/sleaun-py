
grammar Expr;

program: expr* EOF;

expr: '(' expr ')' # Paren
	| expr '(' (expr (',' expr)*)? ')' # Call
	| expr '[' expr ']' # Index
	| ('+' | '-') expr # Unary
	| expr op=('*' | '/') expr # Binary
	| expr op=('+' | '-') expr # Binary
	| <assoc=right> expr '?' expr ':' expr # Ternary
	| <assoc=right> ID ':=' expr # Create
	| <assoc=right> expr '=' expr # Assign
	| atom # Single
	;

atom: ID # Id
	| FLOAT # Float
	| INT # Int
	| STRNG # String
	| '[' (expr (',' expr)*)? ']' # Array
	;

INT: [0-9]+;
FLOAT: [0-9]+ '.' [0-9]+;
STRNG: '"' .*? '"';
ID: [a-zA-Z_][a-zA-Z0-9_]*;

WS: [ \t\n\r]+ -> skip;
COM: ('//' ~[\n]* | '/*' .*? '*/') -> skip;
