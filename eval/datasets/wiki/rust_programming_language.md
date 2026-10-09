# Rust (programming language)

Rust is a general-purpose programming language that emphasizes performance, type safety, concurrency, and memory safety. Rust supports multiple programming paradigms. It was influenced by ideas from functional programming, including immutability, higher-order functions, algebraic data types, and pattern matching. It also supports object-oriented programming via structs, enums, traits, and methods. Rust enforces memory safety (i.e., that all references point to valid memory) without a conventional garbage collector; instead, memory safety errors and data races are prevented by the "borrow checker", which tracks the object lifetime of references at compile time.
Software developer Graydon Hoare created Rust in 2006 while working at Mozilla, which officially sponsored the project in 2009. The first stable release, Rust 1.0, was published in May 2015. The project has been sponsored by the Rust Foundation since February 2021. It has been adopted by many software projects, especially web services and system software. It has been studied academically and has a growing community of developers.


## History


## 2006–2009: Early years

In 2006, Rust began as a personal project by Mozilla employee Graydon Hoare. According to MIT Technology Review, he started the project due to his frustration with a broken elevator in his apartment building whose software had crashed, and named the language after the fungi of the same name that is "over-engineered for survival". Between 2006 and 2009, Rust was not publicized to others at Mozilla and was written in Hoare's free time. Hoare began speaking about the language around 2009 after a small group at Mozilla became interested.
Early contributors have agreed that the language was based primarily on existing ideas. Hoare cited languages from the 1970s, 1980s, and 1990s as influences — including CLU, BETA, Mesa, NIL, Erlang, Newsqueak, Napier, Hermes, Sather, Alef, and Limbo. He described the language as "technology from the past come to save the future from itself." Early contributor Manish Goregaokar similarly described it as based on "mostly decades-old research."
The first compiler was written in about 38,000 lines of OCaml. It supported a number of features no longer present today, including explicit object-oriented programming via an obj keyword and a typestate analysis system tracking variable state such as going from uninitialized to initialized.


## 2009–2012: Mozilla sponsorship
In 2009, Mozilla officially sponsored the project. Brendan Eich and other executives, intrigued by the possibility of using Rust for a safe web browser engine, placed engineers on the project including Patrick Walton, Niko Matsakis, Felix Klock, and Manish Goregaokar. A conference room taken by the project developers was dubbed "the nerd cave," with a sign placed outside the door.
Work shifted from the OCaml compiler to a self-hosting compiler (i.e., written in Rust) targeting LLVM. The ownership system was in place by 2010. The Rust logo was developed in 2011 based on a bicycle chainring. The early 2010s witnessed increasing involvement from full-time engineers at Mozilla and open source contributors.
On January 20, 2012, Rust 0.1 became the first public release for Windows, Linux, and MacOS.


## 2012–2015: Evolution
The following years were marked by substantial changes to the Rust type system. Memory management through the ownership system was gradually consolidated and expanded; by 2013, the garbage collector was rarely used, and was removed. Also removed were typestates, the pure keyword, various specialized pointer types, and syntax support for channels.
According to Steve Klabnik, the language was influenced during this period by developers coming from C++ (e.g., low-level performance of features), scripting languages (e.g., Cargo and package management), and functional programming (e.g., the type system).
In 2013, Graydon Hoare stepped down from Rust. After Hoare's departure, it evolved organically under a federated governance structure, with a "core team" of initially six people, and around 30-40 developers total across various other teams. In March 2014, a Request for Comments (RFC) process for new language features was added. By 2016, the core team would grow to nine people with over 1600 RFCs.
Development focused on finalizing features for version 1.0 (which would begin providing backward compatibility). According to Andrew Binstock writing for Dr. Dobb's Journal in January 2014, while Rust was "widely viewed as a remarkably elegant language", adoption slowed because it radically changed from version to version.
On May 15, 2015, Rust 1.0 became the first stable release. One year later, the compiler had accumulated at least 1,400 contributors, and there were at least 5,000 third-party libraries published on the package management website Crates.io.


## 2015–2020: Servo and early adoption

The development of the Servo browser engine continued in parallel with Rust, funded by Mozilla and Samsung. New features in Rust were tested out by the Servo team, and new features in Servo were used to give feedback back to the Rust team. The first version of Servo was released in 2016. The Firefox web browser shipped with Rust code as of 2016 (version 45), but components of Servo did not appear in Firefox until September 2017 (version 57) as part of the Gecko and Quantum projects.
In the years following 1.0, improvements were made to the toolchain ecosystem including Rustfmt, integrated development environment (IDE) support, and a regular compiler testing and release cycle. Rust's community gained a code of conduct and an IRC chat for discussion.
The earliest known adoption outside of Mozilla was by individual projects at Samsung, Facebook (now Meta Platforms), Dropbox, and Tilde, Inc., the company behind ember.js. Amazon Web Services followed in 2020. Engineers cited performance, lack of a garbage collector, safety, and developer experience as reasons for the adoption. Amazon developers cited a 2017 research finding that Rust code was more energy efficient compared to similar Java code.


## 2020–present: Mozilla layoffs and Rust Foundation
In August 2020, Mozilla laid off 250 of its 1,000 employees as part of a corporate restructuring during the COVID-19 pandemic. The Servo team was disbanded. The event raised concerns about the future of Rust. The Rust Core Team acknowledged the impact of the layoffs and announced plans for an independent foundation. Its first goal would be to own and take financial responsibility for trademarks and domain names.
On February 8, 2021, the Rust Foundation was formed by founding companies Amazon Web Services, Google, Huawei, Microsoft, and Mozilla. The foundation would support developers financially through grants and server funding. In an April 6, 2021 blog post, Google announced support for Rust within the Android Open Source Project. Facebook (Meta Platforms) joined the foundation in April 2021, followed by ARM (Arm Holdings) in November.
On November 22, 2021, the Moderation Team, responsible for enforcing the community code of conduct, resigned "in protest of the Core Team placing themselves unaccountable to anyone but themselves". In May 2022, the Rust leadership council published a response to the incident.
The Rust Foundation posted a draft for a new trademark policy on April 6, 2023 that resulted in widespread negative reactions. The trademark policy included rules for how the Rust logo and name could be used.
In June 2026, OpenAI joined the Rust Foundation.


## Syntax and features

Rust's syntax is similar to that of C and C++, although many of its features were influenced by functional programming languages such as OCaml. Hoare has described Rust as targeted at frustrated C++ developers.


## Hello World program
Below is a "Hello, World!" program in Rust. The fn keyword denotes a function, and the println! macro (see § Macros) prints the message to standard output. Statements in Rust are separated by semicolons.


## Variables
Variables in Rust are defined through the let keyword. The example below assigns a value to the variable with name foo of type i32 and outputs its value; the type annotation : i32 can be omitted.

Variables are immutable by default, unless the mut keyword is added. The following example uses //, which denotes the start of a comment.

Multiple let expressions can define multiple variables with the same name, known as variable shadowing. Variable shadowing allows transforming variables without having to name the variables differently. The example below declares a new variable with the same name that is double the original value:

Variable shadowing is also possible for values of different types. For example, going from a string to its length:


## Block expressions and control flow
A block expression is delimited by curly brackets. When the last expression inside a block does not end with a semicolon, the block evaluates to the value of that trailing expression:

Trailing expressions of function bodies are used as the return value:


## if expressions
An if conditional expression executes code based on whether the given value is true. else can be used for when the value evaluates to false, and else if can be used for combining multiple expressions.

if and else blocks can evaluate to a value, which can then be assigned to a variable:


## while loops
while can be used to repeat a block of code while a condition is met.


## for loops and iterators
For loops in Rust loop over elements of a collection.
for expressions work over any iterator type.

In the above code, 4..=10 is a value of type Range that implements the Iterator trait. The code within the curly braces is applied to each element returned by the iterator.
Iterators can be combined with functions over iterators like map, filter, and sum. For example, the following adds up all numbers between 1 and 100 that are multiples of 3:


## loop and break statements
More generally, the loop keyword allows repeating a portion of code until a break occurs. break may optionally exit the loop with a value. In the case of nested loops, labels denoted by 'label_name can be used to break an outer loop rather than the innermost loop.


## Pattern matching
The match and if let expressions can be used for pattern matching. For example, match can be used to double an optional integer value if present, and return zero otherwise:

Equivalently, this can be written with if let and else:


## Types
Rust is strongly typed and statically typed, meaning that the types of all variables must be known at compilation time. Assigning a value of a particular type to a differently typed variable causes a compilation error. Type inference is used to determine the type of variables if unspecified.
The unit type, notated () in Rust, is a concrete type that has exactly one value. It occupies no memory (as it represents the absence of value). All functions that do not have an indicated return type implicitly return (). It is similar to void in other C-style languages; however, void denotes the absence of a type and cannot have any value.
The default integer type is i32, and the default floating point type is f64. If the type of a literal number is not explicitly provided, it is either inferred from the context or the default type is used.


## Primitive types
Integer types in Rust are named based on the signedness and the number of bits the type takes. For example, i32 is a signed integer that takes 32 bits of storage, whereas u8 is unsigned and only takes 8 bits of storage. isize and usize take storage depending on the memory address bus width of the compilation target. For example, when building for 32-bit targets, both types will take up 32 bits of space.
By default, integer literals are in base-10, but different radices are supported with prefixes, for example, 0b11 for binary numbers, 0o567 for octals, and 0xDB for hexadecimals. By default, integer literals default to i32 as its type. Suffixes such as 4u32 can be used to explicitly set the type of a literal. Byte literals such as b'X' are available to represent the ASCII value (as a u8) of a specific character.
The Boolean type is referred to as bool which can take a value of either true or false. A char takes up 32 bits of space and represents a Unicode scalar value: a Unicode codepoint that is not a surrogate. IEEE 754 floating point numbers are supported with f32 for single precision floats and f64 for double precision floats.


## Compound types
Compound types can contain multiple values. Tuples are fixed-size lists that can contain values whose types can be different. Arrays are fixed-size lists whose values are of the same type. Expressions of the tuple and array types can be written through listing the values, and can be accessed with .index (with tuples) or [index] (with arrays):

Arrays can also be constructed through copying a single value a number of times:


## Ownership and references
Rust's ownership system consists of rules that ensure memory safety without using a garbage collector. At compile time, each value must be attached to a variable called the owner of that value, and every value must have exactly one owner. Values are moved between different owners through assignment or passing a value as a function parameter. Values can also be borrowed, meaning they are temporarily passed to a different function before being returned to the owner. With these rules, Rust can prevent the creation and use of dangling pointers:

The function print_string takes ownership over the String value passed in; Alternatively, & can be used to indicate a reference type (in &String) and to create a reference (in &s):

Because of these ownership rules, Rust types are known as affine types, meaning each value may be used at most once. This enforces a form of software fault isolation as the owner of a value is solely responsible for its correctness and deallocation.
When a value goes out of scope, it is dropped by running its destructor. The destructor may be programmatically defined through implementing the Drop trait. This helps manage resources such as file handles, network sockets, and locks, since when objects are dropped, the resources associated with them are closed or released automatically.


## Lifetimes
Object lifetime refers to the period of time during which a reference is valid; that is, the time between the object creation and destruction. These lifetimes are implicitly associated with all Rust reference types. While often inferred, they can also be indicated explicitly with named lifetime parameters (often denoted 'a, 'b, and so on).
A value's lifetime in Rust is inferred from the set of locations in the source code (i.e., function, line, and column numbers) for which a variable is valid. For example, a reference to a local variable has a lifetime from the expression it is declared in up until the last use of it.

The borrow checker in the Rust compiler then enforces that references are only used in the locations of the source code where the associated lifetime is valid. In the example above, storing a reference to variable x in r is valid, as variable x has a longer lifetime ('a) than variable r ('b). However, when x has a shorter lifetime, the borrow checker would reject the program:

Since the lifetime of the referenced variable ('b) is shorter than the lifetime of the variable holding the reference ('a), the borrow checker errors, preventing x from being used from outside its scope.
Lifetimes can be indicated using explicit lifetime parameters on function arguments. For example, the following code specifies that the reference returned by the function has the same lifetime as original (and not necessarily the same lifetime as prefix):

In the compiler, ownership and lifetimes work together to prevent memory safety issues such as dangling pointers.


## User-defined types
User-defined types are create