# Swift (programming language)

Swift is a high-level general-purpose, multi-paradigm, compiled programming language created by Chris Lattner in 2010 for Apple Inc. and maintained by the open-source community. Swift compiles to machine code and uses an LLVM-based compiler. Swift was first released in June 2014 and the Swift toolchain has shipped in Xcode since Xcode version 6, released in September 2014.
Apple intended Swift to support many core concepts associated with Objective-C, notably dynamic dispatch, widespread late binding, extensible programming, and similar features, but in a "safer" way, making it easier to catch software bugs; Swift has features addressing some common programming errors like null pointer dereferencing and provides syntactic sugar to help avoid the pyramid of doom. Swift supports the concept of protocol extensibility, an extensibility system that can be applied to types, structs and classes, which Apple promotes as a real change in programming paradigms they term "protocol-oriented programming" (similar to traits and type classes).
Swift was introduced at Apple's 2014 Worldwide Developers Conference (WWDC). It underwent an upgrade to version 1.2 during 2014 and a major upgrade to Swift 2 at WWDC 2015. It was initially a proprietary language, but version 2.2 was made open-source software under the Apache License 2.0 on December 3, 2015, for Apple's platforms and Linux.


## History

Development of Swift started in July 2010 by Chris Lattner, with the eventual collaboration of many other programmers at Apple. Swift was motivated by the need for a replacement for Apple's earlier programming language Objective-C, which had been largely unchanged since the early 1980s and lacked modern language features. Swift took language ideas "from Objective-C, Rust, Haskell, Ruby, Python, C#, CLU, and far too many others to list". On June 2, 2014, the Apple Worldwide Developers Conference (WWDC) application became the first publicly released app written with Swift. A beta version of the programming language was released to registered Apple developers at the conference, but the company did not promise that the final version of Swift would be source code compatible with the test version. Apple planned to make source code converters available if needed for the full release.
The Swift Programming Language, a free 500-page manual, was also released at WWDC, and is available on the Apple Books Store and the official website.
Swift reached the 1.0 milestone on September 9, 2014, with the Gold Master of Xcode 6.0 for iOS. Swift 1.1 was released on October 22, 2014, alongside the launch of Xcode 6.1. Swift 1.2 was released on April 8, 2015, along with Xcode 6.3. Swift 2.0 was announced at WWDC 2015, and was made available for publishing apps in the App Store on September 21, 2015.
Swift 3.0 was released on September 13, 2016. Through version 3.0, the syntax of Swift went through significant evolution, with the core team making source stability a focus in later versions.
Swift 4.0, released on September 19, 2017, introduced several changes to some built-in classes and structures. Code written with previous versions of Swift can be updated using the migration functionality built into Xcode. Swift 4.1 was released on March 29, 2018. In the first quarter of 2018, Swift surpassed Objective-C in measured popularity.
Swift 5, released in March 2019, introduced a stable binary interface on Apple platforms, allowing the Swift runtime to be incorporated into Apple operating systems. It is source compatible with Swift 4.
Swift 5.1 was officially released in September 2019. Swift 5.1 builds on the previous version of Swift 5 by extending the stable features of the language to compile-time with the introduction of module stability. The introduction of module stability makes it possible to create and share binary frameworks that will work with future releases of Swift. Swift 5.5, officially announced by Apple at the 2021 WWDC, significantly expands language support for concurrency and asynchronous code, notably introducing a unique version of the actor model. Swift 5.9, was released in September 2023 and includes a macro system, generic parameter packs, and ownership features like the new consume operator. Swift 5.10, released in March 2024, improves the language's concurrency model, allowing for full data isolation to prevent data races.
Swift 6 was released in September 2024. Swift 6.1 was released in March 2025. It includes "new language enhancements to improve productivity, diagnostics improvements, package traits, and ongoing work to improve data-race safety usability and compile times."
Swift won first place for Most Loved Programming Language in the Stack Overflow Developer Survey 2015 and second place in 2016.
On December 3, 2015, the Swift language, supporting libraries, debugger, and package manager were open-sourced under the Apache 2.0 license with a Runtime Library Exception, and Swift.org was created to host the project. The source code is hosted on GitHub, where it is easy for anyone to get the code, build it themselves, and even create pull requests to contribute code back to the project.
In December 2015, IBM announced its Swift Sandbox website, which allows developers to write Swift code in one pane and display output in another. The Swift Sandbox was deprecated in January 2018.
During the WWDC 2016, Apple announced an iPad exclusive app, named Swift Playgrounds, intended to teach people how to code in Swift. The app is presented in a 3D video game-like interface which provides feedback when lines of code are placed in a certain order and executed.
In January 2017, Chris Lattner announced his departure from Apple for a new position with Tesla Motors, with the Swift project lead role going to team veteran Ted Kremenek.
During WWDC 2019, Apple announced SwiftUI with Xcode 11, which provides a framework for declarative UI structure design across all Apple platforms.
Official downloads of the SDK and toolchain for the Ubuntu distribution of Linux have been available since Swift 2.2, with more distros added since Swift 5.2.4, CentOS and Amazon Linux. There is an unofficial SDK and native toolchain package for Android, and in October 2025 Swift's Android workgroup announced a preview release of the official Swift SDK for Android.


## Platforms
The platforms Swift supports are Apple's operating systems (Darwin, iOS, iPadOS, macOS, tvOS, watchOS), Linux, Windows, WebAssembly, and Android.
A key aspect of Swift's design is its ability to interoperate with the huge body of existing Objective-C code developed for Apple products over the previous decades, such as Cocoa and the Cocoa Touch frameworks. On Apple platforms, it links with the Objective-C runtime library, which allows C, Objective-C, C++ and Swift code to run within one program.


## Version history


## Features
Swift is a general-purpose programming language that employs modern programming-language theory concepts and strives to present a simple, yet powerful syntax. Swift incorporates innovations and conventions from various programming languages, with notable inspiration from Objective-C, which it replaced as the primary development language on Apple platforms.
Swift was designed to be safe and friendly to new programmers while not sacrificing speed. By default Swift manages all memory automatically and ensures variables are always initialized before use. Array accesses are checked for out-of-bounds errors and integer operations are checked for overflow. Parameter names allow creating clear APIs. Protocols define interfaces that types may adopt, while extensions allow developers to add more function to existing types. Swift enables object-oriented programming with the support for classes, subtyping, and method overriding. Optionals allow nil values to be handled explicitly and safely. Concurrent programs can be written using async/await syntax, and actors isolate shared mutable state in order to eliminate data races.


## Basic syntax
Swift's syntax is similar to C-style languages. Code begins executing in the global scope by default. Alternatively, the @main attribute can be applied to a structure, class, or enumeration declaration to indicate that it contains the program's entry point.

Swift's "Hello, World!" program is:The print(_:separator:terminator:) function used here is included in Swift's standard library, which is available to all programs without the need to import external modules. Statements in Swift don't have to end with a semicolon, however semicolons are required to separate multiple statements written on the same line. Single-line comments begin with // and continue until the end of the current line. Multiline comments are contained by /* and */ characters.
Constants (variables which cannot be modified) are declared with the let keyword, while variables declared using the var keyword can change. Values must be initialised before they are read. Variables may infer their type based on the type of the provided initial value. If the initial value is set after the value's declaration, a type must be declared explicitly.Control flow in Swift is managed with if-else, guard, and switch statements, along with while and for-in loops.
The if statements take a Boolean parameter and execute the body of the if statement if the condition is true, otherwise it executes the optional else body. if-let syntax provides syntactic sugar for checking for the existence of an optional value and unwrapping it at the same time.Functions are defined with the func keyword. Function parameters may have names which allow function calls to read like phrases. An underscore before the parameter name allows the argument label to be omitted from the call site. Tuples can be used by functions to return multiple pieces of data at once.Functions, and anonymous functions known as closures, can be assigned to properties and passed around the program like any other value.guard statements require that the given condition is true before continuing on past the guard statement, otherwise the body of the provided else clause is run. The else clause must exit control of the code block in which the guard statement appears. guard statements are useful for ensuring that certain requirements are met before continuing on with program execution. In particular they can be used to create an unwrapped version of an optional value that is guaranteed to be non-nil for the remainder of the enclosing scope.switch statements compare a value with multiple potential values and then executes an associated code block. switch statements must be made exhaustive, either by including cases for all possible values or by including a default case which is run when the provided value doesn't match any of the other cases. switch cases do not implicitly fall through, although they may explicitly do so with the fallthrough keyword. Pattern matching can be used in various ways inside switch statements. Here is an example of an integer being matched against a number of potential ranges:for-in loops iterate over a sequence of values:while loops iterate as long as the given Boolean condition evaluates to true:


## Closure support
Swift supports closures, which are self-contained blocks of functionality that can be passed around and used in code, and can also be used as anonymous functions. Here are some examples:

Closures can be assigned to variables and constants, and can be passed into other functions or closures as parameters. Single-expression closures may drop the return keyword.
Swift also has a trailing closure syntax, which allows the closure to be written after the end of the function call instead of within the function's parameter list. Parentheses can be omitted altogether if the closure is the function's only parameter:

Starting from version 5.3, Swift supports multiple trailing closures:

Swift will provide shorthand argument names for inline closures, removing the need to explicitly name all of the closures parameters. Arguments can be referred to with the names $0, $1, $2, and so on:Closures may capture values from their surrounding scope. The closure will refer to this captured value for as long as the closure exists:


## String support
The Swift standard library includes unicode-compliant String and Character types. String values can be initialized with a String literal, a sequence of characters surrounded by double quotation marks. Strings can be concatenated with the + operator:

String interpolation allows for the creation of a new string from other values and expressions. Values written between parentheses preceded by a \ will be inserted into the enclosing string literal:
A for-in loop can be used to iterate over the characters contained in a string:
If the Foundation framework is imported, Swift invisibly bridges the String type to NSString (the String class commonly used in Objective-C).


## Callable objects


## Access control
Swift supports five access control levels for symbols: open, public, internal, fileprivate, and private. Unlike many object-oriented languages, these access controls ignore inheritance hierarchies: private indicates that a symbol is accessible only in the immediate scope, fileprivate indicates it is accessible only from within the file, internal indicates it is accessible within the containing module, public indicates it is accessible from any module, and open (only for classes and their methods) indicates that the class may be subclassed outside of the module.


## Optionals and chaining
An important feature in Swift is option types, which allow references or values to operate in a manner similar to the common pattern in C, where a pointer may either refer to a specific value or no value at all. This implies that non-optional types cannot result in a null-pointer error; the compiler can ensure this is not possible.
Optional types are created with the Optional enum. To make an Integer that is nullable, one would use a declaration similar to var optionalInteger: Optional<Int>. As in C#, Swift also includes syntactic sugar for this, allowing one to indicate a variable is optional by placing a question mark after the type name, var optionalInteger: Int?. Variables or constants that are marked optional either have a value of the underlying type or are nil. Optional types wrap the base type, resulting in a different instance. String and String? are fundamentally different types, the former is of type String while the latter is an Optional that may be holding some String value.
To access the value inside, assuming it is not nil, it must be unwrapped to expose the instance inside. This is performed with the ! operator:

In this case, the ! operator unwraps anOptionalInstance to expose the instance inside, allowing the method call to be made on it. If anOptionalInstance is nil, a null-pointer error occurs, terminating the program. This is known as force unwrapping. Optionals may be safely unwrapped using optional chaining, which first tests whether the instance is nil, and then unwraps it if it is not:

In this case the runtime calls someMethod only if anOptionalInstance is not nil, suppressing the error. A ? must be placed after every optional property. If any of these properties are nil the entire expression evaluates as nil. The origin of the term chaining comes from the more common case where several method calls/getters are chained together. For instance:

can be reduced to:

Swift's use of optionals allows the compiler to use static dispatch because the unwrapping action is called on a defined instance (the wrapper), versus occurring in a runtime dispatch system.


## Value types
In many object-oriented languages, objects are represented internally in two parts. The object is stored as a block of data placed on the heap, while the name (or "handle") to that object is represented by a pointer. Objects are passed between methods by copying the