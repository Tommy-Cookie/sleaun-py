
grammar Expr;

program: expr* EOF;

expr: '(' expr ')' # Paren
	| expr '(' (expr (',' expr)*)? ')' # Call
	| ('+' | '-') expr # Unary
	| expr op=('*' | '/') expr # Binary
	| expr op=('+' | '-') expr # Binary
	| ID ':=' expr # Create
	| atom # Single
	;

atom: FLOAT # Float
	| INT # Int
	| STRNG # String
	| ID # Id
	;

INT: [0-9]+;
FLOAT: [0-9]+ '.' [0-9]+;
STRNG: '"' .*? '"';
ID: [a-zA-Z_][a-zA-Z0-9_]*;

WS: [ \t\n\r]+ -> skip;
COM: ('//' ~[\n]* | '/*' .*? '*/') -> skip;
