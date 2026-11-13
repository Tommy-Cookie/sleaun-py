
grammar Expr;

program: (expr ';')* EOF;

expr: '(' expr ')' # Paren
	| expr '(' (expr (',' expr)*)? ')' # Call
	| expr '[' expr ']' # Index
	| expr '.' ID # Attr
	| op=('+' | '-' | '~' | '!') expr # Unary
	| expr '{' (arm ',')+ '}' # Match
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

atom: ID # Id
	| FLOAT # Float
	| INT # Int
	| STRING # String
	| '[' (expr (',' expr )*)? ']' # Array
	| '{' (expr ';')* '}' # Block
	| '{' (entry (',' entry )*)? ','? '}' # Map
	| <assoc=right> ID '(' (ID (',' ID)*)? ')' '=>' expr # NamedFn
	| <assoc=right> '(' (ID (',' ID)*)? ')' '=>' expr # AnonyFn
	;

arm: atom '->' expr;
entry: atom ':' expr;

INT: [0-9]+;
FLOAT: [0-9]+ '.' [0-9]+;
STRING: '"' .*? '"';
ID: [a-zA-Z_][a-zA-Z0-9_]*;

WS: [ \t\r\n]+ -> skip;
COM: ('//' ~[\n]* | '/*' .*? '*/') -> skip;
