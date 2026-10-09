# Kotlin

Kotlin () is a cross-platform, statically typed, general-purpose high-level programming language with type inference. Kotlin is designed to interoperate fully with Java, and the Java virtual machine (JVM) version of Kotlin's standard library depends on the Java Class Library. Type inference allows for more concise syntax than Java, while null-safety features reduce a common class of runtime errors. Kotlin mainly targets the JVM, but also compiles to JavaScript (e.g., for frontend web applications using React) or native code via LLVM (e.g., for native iOS apps sharing business logic with Android apps). JetBrains bears language development costs, while the Kotlin Foundation protects the Kotlin trademark.
On 7 May 2019, Google announced Kotlin had become its preferred language for Android app developers. As of 2024, over 95% of the top 1,000 Android apps on Google Play contain Kotlin code. In May 2024, JetBrains released Kotlin 2.0 featuring the new K2 compiler—a complete rewrite offering up to twice the compilation speed of its predecessor—as well as stabilised support for Kotlin Multiplatform. That same month, Google formally endorsed Kotlin Multiplatform at Google I/O 2024, recommending it as the approach for sharing business logic across Android, iOS, and other platforms.


## History


## Name
The name is derived from Kotlin Island, a Russian island in the Gulf of Finland, near Saint Petersburg. Andrey Breslav, Kotlin's former lead designer, mentioned that the team decided to name it after an island, in imitation of the Java programming language, which shares a name with the Indonesian island of Java.


## Development
The first commit to the Kotlin Git repository was on 8 November 2010.
In July 2011, JetBrains unveiled Project Kotlin, a new JVM language that had been under development for a year. JetBrains lead Dmitry Jemerov said that most languages lacked the features they were looking for, except for Scala. However, he cited Scala's slow compilation time as a deficiency. One of Kotlin's stated goals is to compile as quickly as Java. In February 2012, JetBrains open-sourced the project under the Apache 2 license.
Kotlin 1.0 was released on 15 February 2016, which is considered the first officially stable release, and JetBrains has committed to long-term backwards compatibility starting with this version.
At Google I/O 2017, Google announced first-class support for Kotlin on Android. On 7 May 2019, Google announced that Kotlin is now its preferred language for Android app developers.
In November 2023, Kotlin/Native was declared stable with version 1.9.20, enabling production-ready compilation to native binaries for iOS, macOS, Linux, and Windows without a JVM. Kotlin Multiplatform (KMP), which allows sharing business logic across Android, iOS, server, and desktop from a single codebase, also reached stable status in November 2023.
In May 2024, JetBrains released Kotlin 2.0 at KotlinConf 2024 as the most significant release in the language's history. The centrepiece was the stable K2 compiler—a complete rewrite of the original compiler frontend from scratch—which unifies all target platforms (JVM, JavaScript, WebAssembly, and Native) into a single pipeline. The K2 compiler was validated against 10 million lines of code across 80,000 projects by more than 18,000 developers before release. Benchmarks showed compilation speed improvements of up to 94% in some projects, with the analysis phase up to 376% faster than the previous compiler. Also in May 2024, Google officially endorsed Kotlin Multiplatform at Google I/O 2024, announcing first-class tooling and library support for KMP on Android, and revealing that Google Workspace uses KMP for the shared business logic of Google Docs across Android, iOS, and web.


## Design
Development lead Andrey Breslav has said that Kotlin is designed to be an industrial-strength object-oriented language, a "better language" than Java, and still fully interoperable with Java code, allowing companies to make a gradual migration from Java to Kotlin.
Semicolons are optional as a statement terminator; in most cases, a newline is sufficient for the compiler to deduce that the statement has ended.
Kotlin variable declarations and parameter lists place the data type after the variable name (separated by a colon), similar to Ada, BASIC, Pascal, TypeScript, and Rust. This, according to an article from Roman Elizarov, current project lead, results in alignment of variable names and is more pleasing to the eyes, especially when there are a few variable declarations in succession, and one or more of the types are too complex for type inference, or need to be declared explicitly for human readers to understand.
The influence of Scala in Kotlin can be seen in the extensive support for both object-oriented and functional programming and in several specific features:

There is a distinction between mutable and immutable variables (var vs val keyword)
All classes are public and final (non-inheritable) by default
Functions and methods support default arguments, variable-length argument lists, and named arguments
Kotlin 1.3 added support for contracts, which are stable for the standard library declarations, but still experimental for user-defined declarations. Contracts are inspired by the design-by-contract programming paradigm.
Like Scala.js, Kotlin code can be transpiled to JavaScript, enabling interoperability between Kotlin and JavaScript and allowing either writing complete web applications in Kotlin or sharing code between a Kotlin backend and a JavaScript frontend.


## Syntax


## Procedural programming style
Kotlin relaxes the Java restriction on static methods and variables, allowing them to exist outside a class body. Static objects and functions can be defined at the top level of the package without requiring a redundant class-level scope. For compatibility with Java, Kotlin provides the JvmName annotation, which specifies the class name used when the package is viewed from a Java project. For example, @file:JvmName("JavaClassName").


## Main entry point

As in C, C++, C#, Java, and Go, the entry point to a Kotlin program is a function named main, which may be passed an array containing any command-line arguments. This is optional since Kotlin 1.3. Perl, PHP, and Unix shell–style string interpolation is supported. Type inference is also supported.


## Visibility modifiers
Kotlin provides the following keywords to restrict visibility for top-level declarations (such as classes) and for class members: public, internal, protected, and private.
When applied to a class member:

When applied to a top-level declaration:

Example:


## Null safety
Kotlin distinguishes between nullable and non-nullable data types. All nullable objects must be declared with a "?" postfix after the type name. Operations on nullable objects need special care from developers: a null-check must be performed before using the value, either explicitly, or with the aid of Kotlin's null-safe operators:

?. (the safe navigation operator) can be used to safely access a method or property of a possibly null object. If the object is null, the method will not be called, and the expression evaluates to null.  Example:

?: (the null coalescing operator) is a binary operator that returns the first operand, if non-null, else the second operand. It is often referred to as the Elvis operator, due to its resemblance to an emoticon representation of Elvis Presley.


## Lambdas
Kotlin supports higher-order functions and anonymous functions, or lambdas.
Lambdas are declared using braces, {  }. If a lambda takes parameters, they are declared within the braces and followed by the -> operator.


## Tools

Android Studio (based on IntelliJ IDEA) has official support for Kotlin since Android Studio 3.
Integration with common Java build tools is supported, including Apache Maven, Apache Ant, and Gradle.
Emacs has a Kotlin Mode in its MELPA package repository.
JetBrains also provides a plugin for Eclipse.
IntelliJ IDEA has plugin-based support for Kotlin. IntelliJ IDEA 15 was the first version to bundle the Kotlin plugin in the IntelliJ Installer and to provide Kotlin support out of the box.
Kotlin integrates seamlessly with Gradle, a build automation tool.


## Kotlin Multiplatform

Kotlin Multiplatform enables a single codebase across mobile, web, server-side and desktop, including Android, iOS, Microsoft Windows, Linux distributions, and other platforms.
KMP reached stable status in November 2023, and at Google I/O 2024, Google recommended it as the standard approach for sharing business logic across Android and iOS, also disclosing that Google Workspace uses KMP for the shared layer of Google Docs on Android, iOS, and web.
Compose Multiplatform is an open-source, declarative framework for sharing UIs across multiple platforms – Android, iOS, web and desktop. It is based on Jetpack Compose and Kotlin Multiplatform. Jetpack Compose uses a Kotlin compiler plugin to transform composable functions into UI elements.  For example, the Text composable function displays a text label on the screen.


## Adoption
In 2018, Kotlin was the fastest-growing language on GitHub, with 2.6 times as many developers as in 2017. It is the fourth-most-loved programming language according to the 2020 Stack Overflow Developer Survey. In GitHub’s 2024 Octoverse report, Kotlin ranked fifth among the fastest-growing programming languages on the platform.
Kotlin was also awarded the O'Reilly Open Source Software Conference Breakout Award for 2019.
A large number of companies in various industries use Kotlin, including Google, Amazon Web Services, Booking.com and McDonald's. Organisations using KMP in production include Forbes, Philips, McDonald's, and Square.
According to the 2024 Stack Overflow Developer Survey, Kotlin ranked among the top admired programming languages, with approximately 57% of developers who used it in the prior year wishing to continue doing so. The JetBrains Developer Ecosystem Survey 2024, conducted among more than 23,000 developers worldwide, found that Kotlin ranked among the highest-paid programming languages globally, alongside Scala, Go, and Rust. 


## Applications
When Kotlin was announced as an official Android development language at Google I/O in May 2017, it became the third language fully supported for Android, after Java and C++. Kotlin on Android is seen as beneficial for its null-safety and features that make code shorter and more readable.
Ktor is a JetBrains Kotlin-first framework for building server and client applications. The Spring Framework officially added Kotlin support with version 5, on 4 January 2017. To further support Kotlin, Spring has translated all its documentation into Kotlin and added built-in support for many Kotlin-specific features, such as coroutines.
In 2020, JetBrains found in a survey of developers who use Kotlin that 56% used it for mobile apps, while 47% used it for a web backend. Just over a third of all Kotlin developers said they were migrating from another language. Most Kotlin users targeted Android (or the JVM), with only 6% using Kotlin Native.
As of 2024, over 95% of the top 1,000 Android apps on Google Play contain Kotlin code.
By 2024, with Kotlin Multiplatform reaching stable status, that picture had shifted: a 2024 community survey of KMP developers found that nearly a quarter of respondents had adopted KMP within the prior six months, indicating strong recent growth, while a further 21% had used it for between one and three years. Google also reported at KotlinConf 2024 that it had migrated the shared business logic of Google Docs to KMP, running in production across Android, iOS, and the web. 


## See also

Comparison of programming languages
List of Java software and tools
Outline of the Java programming language


## References
This article contains quotations from Kotlin tutorials which are released under an Apache 2.0 license.


## External links
Official website