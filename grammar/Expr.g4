
grammar Expr;

program: SEP* (expr (SEP+ expr)*)? SEP* EOF;

expr: '(' expr ')' # Paren
	| expr '(' (expr (',' expr)*)? ')' # Call
	| expr '[' expr ']' # Index
	| ('+' | '-') expr # Unary
	| expr '{' SEP* (arm (SEP+ arm)*) SEP* '}' # Match
	| expr op=('*' | '/') expr # Binary
	| expr op=('+' | '-') expr # Binary
	| <assoc=right> expr op=('+=' | '-=' | '*=' | '/=') expr # InPlace
	| expr op=('<' | '>' | '==' | '<=' | '>=') expr # Binary
	| <assoc=right> expr '?' expr ':' expr # Ternary
	| expr '::' expr # While
	| <assoc=right> ID ':=' expr # Create
	| <assoc=right> expr '=' expr # Assign
	| 'break' expr? # Break
	| 'continue' # Continue
	| 'return' expr? # Return
	| atom # Single
	;

atom: ID # Id
	| FLOAT # Float
	| INT # Int
	| STRING # String
	| '[' (expr (',' expr)*)? ']' # Array
	| '{' SEP* (expr (SEP+ expr)*)? SEP* '}' # Block
	| <assoc=right> ID '(' (ID (',' ID)*)? ')' '=>' expr # NamedFn
	| <assoc=right> '(' (ID (',' ID)*)? ')' '=>' expr # AnonyFn
	;

arm: atom '->' expr;

INT: [0-9]+;
FLOAT: [0-9]+ '.' [0-9]+;
STRING: '"' .*? '"';
ID: [a-zA-Z_][a-zA-Z0-9_]*;
SEP: '\n' | ';';

WS: [ \t\r]+ -> skip;
COM: ('//' ~[\n]* | '/*' .*? '*/') -> skip;
