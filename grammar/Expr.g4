
grammar Expr;

program: expr* EOF;

expr: '(' expr ')' # Paren
	| expr '(' (expr (',' expr)*)? ')' # Call
	| expr '[' expr ']' # Index
	| ('+' | '-') expr # Unary
	| expr op=('*' | '/') expr # Binary
	| expr op=('+' | '-') expr # Binary
	| expr op=('<' | '>' | '==' | '<=' | '>=') expr # Binary
	| <assoc=right> expr '?' expr ':' expr # Ternary
	| expr '{' expr* '}' # While
	| <assoc=right> ID ':=' expr # Create
	| <assoc=right> expr '=' expr # Assign
	| 'break' expr? # Break
	| atom # Single
	;

atom: ID # Id
	| FLOAT # Float
	| INT # Int
	| STRNG # String
	| '[' (expr (',' expr)*)? ']' # Array
	| '{' expr* '}' # Block
	;

INT: [0-9]+;
FLOAT: [0-9]+ '.' [0-9]+;
STRNG: '"' .*? '"';
ID: [a-zA-Z_][a-zA-Z0-9_]*;

WS: [ \t\n\r]+ -> skip;
COM: ('//' ~[\n]* | '/*' .*? '*/') -> skip;
