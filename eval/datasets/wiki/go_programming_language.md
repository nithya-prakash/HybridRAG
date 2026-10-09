# Go (programming language)

Go (often referred to as Golang) is a high-level, general-purpose programming language that is statically typed and compiled. Originally designed in 2007 by Robert Griesemer, Rob Pike, and Ken Thompson, Go was publicly announced in November 2009, and is developed by Google and community contributors. Go has a simple syntax similar to C++, as well as garbage collection, structural typing, CSP-style concurrency, and a broad standard library.
There are two major implementations:

The original, self-hosting compiler toolchain, initially developed inside Google;
A frontend written in C++, called gofrontend, originally a GCC frontend, providing gccgo, a GCC-based Go compiler; later extended to also support LLVM, providing an LLVM-based Go compiler called gollvm.


## History
Go was designed at Google in 2007 to improve programming productivity in an era of multicore, networked machines and large codebases. The designers wanted to address criticisms of other languages in use at Google, but keep their useful characteristics:

Static typing and run-time efficiency (like C)
Readability and usability (like Python)
High-performance networking and multiprocessing
Its designers were primarily motivated by their shared dislike of C++.
Go was publicly announced in November 2009, and version 1.0 was released in March 2012. Go is widely used in production at Google and in many other organizations and open-source projects.
Go developers implemented runtime support for concurrency in response to the availability of multicore systems:

Although the design of most languages concentrates on innovations in syntax, semantics, or typing, Go is focused on the software development process itself. ... The principal unusual property of the language itself—concurrency—addressed problems that arose with the proliferation of multicore CPUs in the 2010s. But more significant was the early work that established fundamentals for packaging, dependencies, build, test, deployment, and other workaday tasks of the software development world, aspects
that are not usually foremost in language design.
As of April 2022, each commit to the Go repository must be approved by two Google employees.


## Branding and styling

The gopher mascot was introduced in 2009 for the open source launch of the language. Renée French, who had designed the rabbit mascot for Plan 9, adapted the gopher from an earlier WFMU T-shirt design. The gopher was originally named Gordon, but it has been nameless since 2010.
In November 2016, the Go and Go Mono fonts were released by type designers Charles Bigelow and Kris Holmes specifically for use by the Go project. Go is a humanist sans-serif resembling Lucida Grande but with near (not full) metric compatibility with Helvetica and Arial, and Go Mono is monospaced. Both fonts adhere to the WGL4 character set and were designed to be legible with a large x-height and distinct letterforms. Both Go and Go Mono adhere to the DIN 1450 standard by having a slashed zero, lowercase l with a tail, and an uppercase I with serifs.
In April 2018, the original logo was redesigned by brand designer Adam Smith. The new logo is a modern, stylized GO slanting right with trailing streamlines. The gopher mascot remained the same.


## Generics
The lack of support for generic programming in initial versions of Go drew considerable criticism. The designers expressed an openness to generic programming and noted that built-in functions were in fact type-generic, but are treated as special cases; Pike called this a weakness that might be changed at some point. The Google team built at least one compiler for an experimental Go dialect with generics, but did not release it.
In August 2018, the Go principal contributors published draft designs for generic programming and error handling and asked users to submit feedback. However, the error handling proposal was eventually abandoned.
In June 2020, a new draft design document was published that would add the necessary syntax to Go for declaring generic functions and types. A code translation tool, go2go, was provided to allow users to try the new syntax, along with a generics-enabled version of the online Go Playground.
Generics were finally added to Go in version 1.18 on March 15, 2022.


## Versioning
Go 1 guarantees compatibility for the language specification and major parts of the standard library. All versions up through the current Go 1.26 release have maintained this promise.
Go uses a go1.[major].[patch] versioning format, such as go1.26.0 and each major Go release is supported until there are two newer major releases. Unlike most software, Go calls the second number in a version the major, i.e., in go1.26.0 the 26 is the major version. This is because Go plans to never reach 2.0, prioritizing backwards compatibility over potential breaking changes.


## Design

Go is influenced by C (especially the Plan 9 dialect), but with an emphasis on greater simplicity and safety. It consists of:

A syntax and environment adopting patterns more common in dynamic languages:
Optional concise variable declaration and initialization through type inference (x := 0 instead of var x int = 0; or var x = 0;)
Fast compilation
Remote package management (go get) and online package documentation
Distinctive approaches to particular problems:
Built-in concurrency primitives: light-weight processes (goroutines), channels, and the select statement
An interface system in place of virtual inheritance, and type embedding instead of non-virtual inheritance
A toolchain that, by default, produces statically linked native binaries without external Go dependencies
A desire to keep the language specification simple enough to hold in a programmer's head, in part by omitting features that are common in similar languages.
25 reserved words


## Syntax
Go's syntax includes changes from C aimed at keeping code concise and readable. A combined declaration/initialization operator was introduced that allows the programmer to write i := 3 or s := "Hello, world!", without specifying the types of variables used. This contrasts with C's int i = 3; and char *s = "Hello, world!"; (though since C23 type inference has been supported using auto, like C++). Go also removes the requirement to use parentheses in if statement conditions.
Semicolons still terminate statements; but are implicit when the end of a line occurs.
Methods may return multiple values, and returning a result, err pair is the conventional way a method indicates an error to its caller in Go. Go adds literal syntaxes for initializing struct parameters by name and for initializing maps and slices. As an alternative to C's three-statement for loop, Go's range expressions allow concise iteration over arrays, slices, strings, maps, and channels.


## Keywords
Go contains the following 25 keywords:


## Types
Go has a number of built-in types, including numeric ones (byte, int64, float32, etc.), Booleans, and byte strings (string). Strings are immutable; built-in operators and keywords (rather than functions) provide concatenation, comparison, and UTF-8 encoding/decoding. Record types can be defined with the struct keyword.
Go contains the following primitives:

Note that byte is an alias for uint8 and rune is an alias for int32.
For each type T and each non-negative integer constant n, there is an array type denoted [n]T; arrays of differing lengths are thus of different types. Dynamic arrays are available as "slices", denoted []T for some type T (compare to other languages like C/C++ and Java, where instead the arrays are denoted T[]). These have a length and a capacity specifying when new memory needs to be allocated to expand the array. Several slices may share their underlying memory.
Pointers are available for all types, and the pointer-to-T type is denoted *T (similar to Rust; compare to other languages like C/C++ and C#, where pointers are denoted T*). Address-taking and indirection use the & and * operators, as in C, or happen implicitly through the method call or attribute access syntax. There is no pointer arithmetic, except via the special unsafe.Pointer type in the standard library.
For a pair of types K, V, the type map[K]V is the type mapping type-K keys to type-V values, which can be thought of as equivalent to Map<K, V> in other languages. The Go Programming Language specification does not give any performance guarantees or implementation requirements for map types, though it is usually implemented as a hash table (equivalent to HashMap<K, V> in other languages). Hash tables are built into the language, with special syntax and built-in functions. chan T is a channel that allows sending values of type T between concurrent Go processes.
Aside from its support for interfaces, Go's type system is nominal: the type keyword can be used to define a new named type, which is distinct from other named types that have the same layout (in the case of a struct, the same members in the same order). Some conversions between types (e.g., between the various integer types) are pre-defined and adding a new type may define additional conversions, but conversions between named types must always be invoked explicitly. For example, the type keyword can be used to define a type for IPv4 addresses, based on 32-bit unsigned integers as follows:

With this type definition, ipv4addr(x) interprets the uint32 value x as an IP address. Simply assigning x to a variable of type ipv4addr is a type error.
Constant expressions may be either typed or "untyped"; they are given a type when assigned to a typed variable if the value they represent passes a compile-time check.
Function types are indicated by the func keyword; they take zero or more parameters and return zero or more values, all of which are typed. The parameter and return values determine a function type; thus, func(string, int32) (int, error) is the type of functions that take a string and a 32-bit signed integer, and return a signed integer (of default width) and a value of the built-in interface type error.
Any named type has a method set associated with it. The IP address example above can be extended with a method for checking whether its value is a known standard:

Due to nominal typing, this method definition adds a method to ipv4addr, but not on uint32. While methods have special definition and call syntax, there is no distinct method type.


## Interface system
Go provides two features that replace class inheritance.
The first is embedding, which can be viewed as an automated form of composition.
The second are its interfaces, which provides runtime polymorphism. Interfaces are a class of types and provide a limited form of structural typing in the otherwise nominal type system of Go. An object which is of an interface type is also of another type, much like C++ objects being simultaneously of a base and derived class. The design of Go interfaces was inspired by protocols from the Smalltalk programming language. Multiple sources use the term duck typing when describing Go interfaces. Although the term duck typing is not precisely defined and therefore not wrong, it usually implies that type conformance is not statically checked. Because conformance to a Go interface is checked statically by the Go compiler (except when performing a type assertion), the Go authors prefer the term structural typing.
The definition of an interface type lists required methods by name and type. Any object of type T for which functions exist matching all the required methods of interface type I is an object of type I as well. The definition of type T need not (and cannot) identify type I. For example, if Shape, Square, and Circle are defined as

then both a Square and a Circle are implicitly a Shape and can be assigned to a Shape-typed variable. In formal language, Go's interface system provides structural rather than nominal typing. Interfaces can embed other interfaces with the effect of creating a combined interface that is satisfied by exactly the types that implement the embedded interface and any methods that the newly defined interface adds.
The Go standard library uses interfaces to provide genericity in several places, including the input/output system that is based on the concepts of Reader and Writer.

Besides calling methods via interfaces, Go allows converting interface values to other types with a run-time type check. The language constructs to do so are the type assertion, which checks against a single potential type:and the type switch, which checks against multiple types:The empty interface interface{} is an important base case because it can refer to an item of any concrete type. It is similar to the Object class in Java or C# or void* in C or Any in C++ and Rust and is satisfied by any type, including built-in types like int. Code using the empty interface cannot simply call methods (or built-in operators) on the referred-to object, but it can store the interface{} value, try to convert it to a more useful type via a type assertion or type switch, or inspect it with Go's reflect package. Because interface{} can refer to any value, it is a limited way to escape the restrictions of static typing, like void* in C but with additional run-time type checks.
The interface{} type can be used to model structured data of any arbitrary schema in Go, such as JSON or YAML data, by representing it as a map[string]interface{} (map of string to empty interface). This recursively describes data in the form of a dictionary with string keys and values of any type.
Interface values are implemented using pointer to data and a second pointer to run-time type information. Like some other types implemented using pointers in Go, interface values are nil if uninitialized.


## Generic code using parameterized types
Since version 1.18, Go supports generic code using parameterized types.
Functions and types now have the ability to be generic using type parameters. These type parameters are specified within square brackets, right after the function or type name. The compiler transforms the generic function or type into non-generic by substituting type arguments for the type parameters provided, either explicitly by the user or type inference by the compiler. This transformation process is referred to as type instantiation.

Interfaces now can define a set of types (known as type set) using | (Union) operator, as well as a set of methods. These changes were made to support type constraints in generics code. For a generic function or type, a constraint can be thought of as the type of the type argument: a meta-type. This new ~T syntax will be the first use of ~ as a token in Go. ~T means the set of all types whose underlying type is T.


## Enumerated types


## Package system
In Go's package system, each package has a path (e.g., "compress/bzip2" or "golang.org/x/net/html") and a name (e.g., bzip2 or html). By default other packages' definitions must always be prefixed with the other package's name. However the name used can be changed from the package name, and if imported as _, then no package prefix is required. Only the capitalized names from other packages are accessible: io.Reader is public but bzip2.reader is not. The go get command can retrieve packages stored in a remote repository and developers are encouraged to develop packages inside a base path corresponding to a source repository (such as example.com/user_name/package_name) to reduce the likelihood of name collision with future additions to the standard library or other external libraries.


## Concurrency: goroutines and channels

The Go language has built-in facilities, as well as library support, for writing concurrent programs. The runtime is asynchronous: program execution that performs, for example, a network read will be suspended until data is available to process, allowing other parts of the program to perform other work. This is built into the runtime an