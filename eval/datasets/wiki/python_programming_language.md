# Python (programming language)

Python is a high-level, general-purpose programming language that emphasizes code readability, simplicity, and ease-of-writing with the use of significant indentation, an extensive ("batteries-included") standard library, and garbage collection. Python supports multiple programming paradigms but with an emphasis on object-oriented programming and dynamic typing.
Guido van Rossum began working on Python in the late 1980s as a successor to the ABC programming language. Python 3.0, released in 2008, was a major revision and not completely backward-compatible with earlier versions. Beginning with Python 3.5, capabilities and keywords for typing were added to the language, allowing optional static typing. As of 2026, the Python Software Foundation supports Python 3.11, 3.12, 3.13, and 3.14, following the project's annual release cycle and five-year support policy. Python 3.15.0rc3 (which defaults to UTF-8) is out in preview, a "surprise third release candidate for Python 3.15.0! .. so this week’s planned 3.15.0 final is postponed until October 9th, 2026" to allow more users to test it. Earlier versions in the 3.x series have reached end-of-life and no longer receive security updates. 
Python is widely taught as an introductory programming language.


## History

Python was conceived in the late 1980s by Guido van Rossum at Centrum Wiskunde & Informatica (CWI) in the Netherlands. It was designed as a successor to the ABC programming language, which was inspired by SETL, capable of exception handling and interfacing with the Amoeba operating system. Python implementation began in December 1989. Van Rossum first released it in 1991 as Python 0.9.0. Van Rossum assumed sole responsibility for the project, as the lead developer, until 12 July 2018, when he announced his "permanent vacation" from responsibilities as Python's "benevolent dictator for life" (BDFL); this title was bestowed on him by the Python community to reflect his long-term commitment as the project's chief decision-maker. In January 2019, active Python core developers elected a five-member Steering Council to lead the project.
The name Python derives from the British comedy series Monty Python's Flying Circus. (See § Naming.)
Python 2.0 was released on 16 October 2000, featuring many new features such as list comprehensions, cycle-detecting garbage collection, reference counting, and Unicode support. Python 2.7's end-of-life was initially set for 2015, and then postponed to 2020 out of concern that a large body of existing code could not easily be forward-ported to Python 3. It no longer receives security patches or updates. While Python 2.7 and older versions are officially unsupported, a different unofficial Python implementation, PyPy, continues to support Python 2, i.e., "2.7.18+" (plus 3.11 and 3.12), with the plus signifying (at least some) "backported security updates".
Python 3.0 was released on 3 December 2008, and was a major revision and not completely backward-compatible with earlier versions, with some new semantics and changed syntax. Python 2.7.18, released in 2020, was the last release of Python 2. Several releases in the Python 3.x series have added new syntax to the language, and made a few (considered very minor) backward-incompatible changes.
As of October 2026, Python 3.14.8  an "expedited security release" is the latest stable release, and since 3.14 official Android binary releases are available. All older 3.x versions had a security update down to  Python 3.10.22. Python 3.11 is, since October 2026, the oldest supported branch. Python 3.15 has release candidate 3 out, it is the final planned release candidate and adds e.g. frozendict and sentinel built-in types, and a new soft keyword, lazy, for lazy imports. Releases receive two years of full support followed by three years of security support.


## Design philosophy and features
Python is a multi-paradigm programming language. Object-oriented programming and structured programming are fully supported, and many of their features support functional programming and aspect-oriented programming – including metaprogramming and metaobjects. Many other paradigms are supported via extensions, including design by contract and logic programming. Python is often referred to as a ‘glue language’ because it is purposely designed to be able to integrate components written in other languages.
Python uses dynamic typing and a combination of reference counting and a cycle-detecting garbage collector for memory management. It uses dynamic name resolution (late binding), which binds method and variable names during program execution.
Python's design offers some support for functional programming in the "Lisp tradition". It has filter, map, and reduce functions; list comprehensions, dictionaries, sets, and generator expressions. The standard library has two modules (itertools and functools) that implement functional tools borrowed from Haskell and Standard ML.
Python's core philosophy is summarized in the Zen of Python (PEP 20) written by Tim Peters, which includes aphorisms such as these:

Explicit is better than implicit.
Simple is better than complex.
Readability counts.
Special cases aren't special enough to break the rules.
Although practicality beats purity, errors should never pass silently, unless explicitly silenced.
There should be one—and preferably only one—obvious way to do it.
However, Python has received criticism for violating these principles and adding unnecessary language bloat. Responses to these criticisms note that the Zen of Python is a guideline rather than a rule. The addition of some new features had been controversial: Guido van Rossum resigned as Benevolent Dictator for Life after conflict about adding the assignment expression operator in Python 3.8.
Nevertheless, rather than building all functionality into its core, Python was designed to be highly extensible through modules. This compact modularity has made it particularly popular as a means of adding programmable interfaces to existing applications. Van Rossum's vision of a small core language with a large standard library and an easily extensible interpreter stemmed from his frustrations with ABC, which represented the opposite approach.
Python claims to strive for a simpler, less-cluttered syntax and grammar, while giving developers a choice in their coding methodology. Python lacks do .. while loops, which Rossum considered harmful. In contrast to Perl's motto "there is more than one way to do it", Python advocates an approach where "there should be one – and preferably only one – obvious way to do it". In practice, however, Python provides many ways to achieve a given goal. There are at least three ways to format a string literal, with no certainty as to which one a programmer should use. Alex Martelli is a Fellow at the Python Software Foundation and Python book author; he wrote that "To describe something as 'clever' is not considered a compliment in the Python culture."
Python's developers typically prioritize readability over performance. For example, they reject patches to non-critical parts of the CPython reference implementation that would offer increases in speed that do not justify the cost of clarity and readability. Execution speed can be improved by moving speed-critical functions to extension modules written in languages such as C, or by using a just-in-time compiler like PyPy. Also, it is possible to transpile to other languages. However, this approach either fails to achieve the expected speed-up, since Python is a very dynamic language, or only a restricted subset of Python is compiled (with potential minor semantic changes).
Python is meant to be a fun language to use. This goal is reflected in the name – a tribute to the British comedy group Monty Python – and in playful approaches to some tutorials and reference materials. For instance, some code examples use the terms "spam" and "eggs" (in reference to a Monty Python sketch), rather than the typical terms "foo" and "bar".
A common neologism in the Python community is pythonic, which has a broad range of meanings related to program style: Pythonic code may use Python idioms well; be natural or show fluency in the language; or conform with Python's minimalist philosophy and emphasis on readability.


## Enhancement Proposals
Python Enhancement Proposals are a design document for either providing information to the Python community, or proposal for new feature in Python. PEPs are intended to explain new processes in Python, provide naming conventions or document the processes in the language. PEPs are overseen by Python Steering Council.
There are 3 kinds of PEPs, with those are being standards track PEP, Informational PEP and Process PEPs which has their own unique meanings. They were firstly introduced in 2000, inspired by other RfCs (requests for comments) and Design Enhancement Proposals. Most known PEPs are PEP – 1, PEP – 8, PEP – 20, PEP – 257 and others.


## Syntax and semantics

Python is meant to be an easily readable language. Its formatting is visually uncluttered and often uses English keywords where other languages use punctuation. Unlike many other languages, it does not use curly brackets to delimit blocks, and semicolons after statements are allowed but rarely used. It has fewer syntactic exceptions and special cases than C or Pascal.


## Indentation

Python uses whitespace indentation, rather than curly brackets or keywords, to delimit blocks. An increase in indentation comes after certain statements; a decrease in indentation signifies the end of the current block. Thus, the program's visual structure accurately represents its semantic structure. This feature is sometimes termed the off-side rule. Some other languages use indentation this way; but in most, indentation has no semantic meaning. The recommended indent size is four spaces.


## Statements and control flow
Python's statements include the following:

The assignment statement, using a single equals sign =
The if statement, which conditionally executes a block of code, along with else and elif (a contraction of else if)
The for statement, which iterates over an iterable object, capturing each element to a variable for use by the attached block; the variable is not deleted when the loop finishes
The while statement, which executes a block of code as long as boolean condition is true
The try statement, which allows exceptions raised in its attached code block to be caught and handled by except clauses (or new syntax except* in Python 3.11 for exception groups); the try statement also ensures that clean-up code in a finally block is always run regardless of how the block exits
The raise statement, used to raise a specified exception or re-raise a caught exception
The class statement, which executes a block of code and attaches its local namespace to a class, for use in object-oriented programming
The def statement, which defines a function or method
The with statement, which encloses a code block within a context manager, allowing resource-acquisition-is-initialization (RAII)-like behavior and replacing a common try/finally idiom Examples of a context include acquiring a lock before some code is run, and then releasing the lock; or opening and then closing a file
The break statement, which exits a loop
The continue statement, which skips the rest of the current iteration and continues with the next
The del statement, which removes a variable—deleting the reference from the name to the value, and producing an error if the variable is referred to before it is redefined
The pass statement, serving as a NOP (i.e., no operation), which is syntactically needed to create an empty code block
The assert statement, used in debugging to check for conditions that should apply
The yield statement, which returns a value from a generator function (and also an operator); used to implement coroutines
The return statement, used to return a value from a function
The import and from statements, used to import modules whose functions or variables can be used in the current program. Python 3.15 adds a new functionality to lazily import with a new keyword: "The lazy keyword works with both import and from ... import statements."
The match and case statements, analogous to a switch statement construct, which compares an expression against one or more cases as a control-flow measure
The assignment statement (=) binds a name as a reference to a separate, dynamically allocated object. Variables may subsequently be rebound at any time to any object. In Python, a variable name is a generic reference holder without a fixed data type; however, it always refers to some object with a type. This is called dynamic typing—in contrast to statically-typed languages, where each variable may contain only a value of a certain type.
Python does not support tail call optimization or first-class continuations; according to Van Rossum, the language never will. However, better support for coroutine-like functionality is provided by extending Python's generators. Before 2.5, generators were lazy iterators; data was passed unidirectionally out of the generator. From Python 2.5 on, it is possible to pass data back into a generator function; and from version 3.3, data can be passed through multiple stack levels.


## Expressions
Python's expressions include the following:

The +, -, and * operators for mathematical addition, subtraction, and multiplication are similar to other languages, but the behavior of division differs. There are two types of division in Python: floor division (or integer division) //, and floating-point division /. Python uses the ** operator for exponentiation.
Python uses the + operator for string concatenation. The language uses the * operator for duplicating a string a specified number of times.
The @ infix operator is intended to be used by libraries such as NumPy for matrix multiplication.
The syntax :=, called the "walrus operator", was introduced in Python 3.8. This operator assigns values to variables as part of a larger expression.
In Python, == compares two objects by value. Python's is operator may be used to compare object identities (i.e., comparison by reference), and comparisons may be chained—for example, a <= b <= c.
Python uses and, or, and not as Boolean operators.
Python has a type of expression called a list comprehension, and a more general expression called a generator expression.
Anonymous functions are implemented using lambda expressions; however, there may be only one expression in each body.
Conditional expressions are written as x if c else y. (This is different in operand order from the c ? x : y operator common to many other languages.)
Python makes a distinction between lists and tuples. Lists are written as [1, 2, 3], are mutable, and cannot be used as the keys of dictionaries (since dictionary keys must be immutable in Python). Tuples, written as (1, 2, 3), are immutable and thus can be used as the keys of dictionaries, provided that all of the tuple's elements are immutable. The + operator can be used to concatenate two tuples, which does not directly modify their contents, but produces a new tuple containing the elements of both. For example, given the variable t initially equal to (1, 2, 3), executing t = t + (4, 5) first evaluates t + (4, 5), which yields (1, 2, 3, 4, 5); this result is then assigned back to t—thereby effectively "modifying the contents" of t while conforming to the immutable nature of tuple objects. Parentheses are optional for tuples in unambiguous contexts.
Python features sequence unpacking where multiple expressions, each evaluating to something assignable (e.g., a variable or a writable property) are associated just as in forming tuple literal; as a whole, the results are then put on the left-hand side of the equal sign in an assignment statement. This statement expects an iterable obj