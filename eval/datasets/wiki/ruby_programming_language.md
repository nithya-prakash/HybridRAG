# Ruby (programming language)

Ruby is a general-purpose programming language designed with an emphasis on programming productivity and simplicity. In Ruby, everything is an object, including primitive data types. Development of the language began in the mid-1990s by Yukihiro "Matz" Matsumoto in Japan.
Ruby is interpreted, high-level, and dynamically typed; its interpreter uses garbage collection and just-in-time compilation. It supports multiple programming paradigms, including procedural, object-oriented, and functional programming. According to the creator, Ruby was influenced by Perl, Smalltalk, Eiffel, Ada, BASIC, and Lisp.


## History


## Early concept
According to Matsumoto, Ruby was conceived in 1993. In a 1999 post to the Ruby-Talk mailing list, he shared some of his early ideas about the language:

I was talking with my colleague about the possibility of an object-oriented scripting language. I knew Perl (Perl4, not Perl5), but I didn't like it really, because it had the smell of a toy language (it still has). The object-oriented language seemed very promising. I knew Python then. But I didn't like it, because I didn't think it was a true object-oriented language –  OO features appeared to be add-on to the language. As a language maniac and OO fan for 15 years, I really wanted a genuine object-oriented, easy-to-use scripting language. I looked for but couldn't find one. So I decided to make it.
Matsumoto described Ruby's design as resembling a simple Lisp language at its core, with an object system like that of Smalltalk, blocks inspired by higher-order functions, and practical utility like that of Perl.
The name "Ruby" originated during an online chat session between Matsumoto and Keiju Ishitsuka on 24 February 1993, before any code had been written. Two names were initially proposed: "Coral" and "Ruby". Matsumoto chose the latter in a subsequent email to Ishitsuka. He also noted that one factor influencing the choice of the name was that a colleague's birthstone was ruby.


## Early releases
The first public release of Ruby 0.95 was announced on Japanese domestic newsgroups on 21 December 1995. Subsequently, three more versions of Ruby were released in two days. The release coincided with the launch of the Japanese-language ruby-list mailing list, which was the first mailing list for the new language.
Already present at this stage of development were many of the features familiar in later releases of Ruby, including object-oriented design, classes with inheritance, mixins, iterators, closures, exception handling and garbage collection.
After the release of Ruby 0.95 in 1995, several stable versions of Ruby were released in these years.
In 1997, the first article about Ruby was published on the Web. In the same year, Matsumoto was hired by netlab.jp to work on Ruby as a full-time developer.
In 1998, the Ruby Application Archive was launched by Matsumoto, along with a simple English-language homepage for Ruby.
In 1999, the first English language mailing list ruby-talk began, which signaled a growing interest in the language outside Japan. In this same year, Matsumoto and Keiju Ishitsuka wrote the first book on Ruby, The Object-oriented Scripting Language Ruby (オブジェクト指向スクリプト言語 Ruby), which was published in Japan in October 1999. It would be followed in the early 2000s by around 20 books on Ruby published in Japanese.
By 2000, Ruby was more popular than Python in Japan. In September 2000, the first English language book Programming Ruby was printed, which was later freely released to the public, further widening the adoption of Ruby amongst English speakers. In early 2002, the English-language ruby-talk mailing list was receiving more messages than the Japanese-language ruby-list, demonstrating Ruby's increasing popularity in the non-Japanese speaking world.


## Ruby 1.8 and 1.9
Ruby 1.8 was initially released in August 2003, was stable for a long time, and was retired in June 2013. Although deprecated, there is still code based on it. Ruby 1.8 is only partially compatible with Ruby 1.9.
Ruby 1.8 has been the subject of several industry standards. The language specifications for Ruby were developed by the Open Standards Promotion Center of the Information-Technology Promotion Agency (a Japanese government agency) for submission to the Japanese Industrial Standards Committee (JISC) and then to the International Organization for Standardization (ISO). It was accepted as a Japanese Industrial Standard (JIS X 3017) in 2011 and an international standard (ISO/IEC 30170) in 2012.

Around 2005, interest in the Ruby language surged in tandem with Ruby on Rails, a web framework written in Ruby. Rails is frequently credited with increasing awareness of Ruby.
Effective with Ruby 1.9.3, released 31 October 2011, Ruby switched from being dual-licensed under the Ruby License and the GPL to being dual-licensed under the Ruby License and the two-clause BSD license. Adoption of 1.9 was slowed by changes from 1.8 that required many popular third party gems to be rewritten.


## Ruby 2
Ruby 2.0 was intended to be fully backward compatible with Ruby 1.9.3. As of the official 2.0.0 release on 24 February 2013, there were only five known incompatibilities.
Starting with 2.1.0, Ruby's versioning policy changed to be more similar to semantic versioning, although it differs slightly in that minor version increments may be API incompatible.
Ruby 2.2.0 includes speed-ups, bugfixes, and library updates and removes some deprecated APIs. Most notably, Ruby 2.2.0 introduces changes to memory handling – an incremental garbage collector, support for garbage collection of symbols and the option to compile directly against jemalloc. It also contains experimental support for using vfork(2) with system() and spawn(), and added support for the Unicode 7.0 specification. Since version 2.2.1, Ruby MRI performance on PowerPC64 was improved. Features that were made obsolete or removed include callcc, the DL library, Digest::HMAC, lib/rational.rb, lib/complex.rb, GServer, Logger::Application as well as various C API functions.
Ruby 2.3.0 includes many performance improvements, updates, and bugfixes including changes to Proc#call, Socket and IO use of exception keywords, Thread#name handling, default passive Net::FTP connections, and Rake being removed from stdlib. Other notable changes include:

The ability to mark all string literals as frozen by default with a consequently large performance increase in string operations.
Hash comparison to allow direct checking of key/value pairs instead of just keys.
A new safe navigation operator &. that can ease nil handling (e.g. instead of if obj && obj.foo && obj.foo.bar, we can use if obj&.foo&.bar).
The did_you_mean gem is now bundled by default and required on startup to automatically suggest similar name matches on a NameError or NoMethodError.
Hash#dig and Array#dig to easily extract deeply nested values (e.g. given profile = { social: { wikipedia: { name: 'Foo Baz' } } }, the value Foo Baz can now be retrieved by profile.dig(:social, :wikipedia, :name)).
.grep_v(regexp) which will match all negative examples of a given regular expression in addition to other new features.
Ruby 2.4.0 includes performance improvements to hash table, Array#max, Array#min, and instance variable access. Other notable changes include:

Binding#irb: Start a REPL session similar to binding.pry
Unify Fixnum and Bignum into Integer class
String supports Unicode case mappings, not just ASCII
A new method, Regexp#match?, which is a faster Boolean version of Regexp#match
Thread deadlock detection now shows threads with their backtrace and dependency
A few notable changes in Ruby 2.5.0 include rescue and ensure statements automatically use a surrounding do-end block (less need for extra begin-end blocks), method-chaining with yield_self, support for branch coverage and method coverage measurement, and easier Hash transformations with Hash#slice and Hash#transform_keys On top of that come a lot of performance improvements like faster block passing (3 times faster), faster Mutexes, faster ERB templates and improvements on some concatenation methods.
A few notable changes in Ruby 2.6.0 include an experimental just-in-time compiler (JIT), and RubyVM::AbstractSyntaxTree (experimental).
A few notable changes in Ruby 2.7.0 include pattern Matching (experimental), REPL improvements, a compaction GC, and separation of positional and keyword arguments.


## Ruby 3
Ruby 3.0.0 was released on Christmas Day in 2020. It is known as Ruby 3x3, which signifies that programs would run three times faster in Ruby 3.0 comparing to Ruby 2.0. and some had already been implemented in intermediate releases on the road from 2 to 3. To achieve 3x3, Ruby 3 comes with MJIT, and later YJIT, Just-In-Time Compilers, to make programs faster, although they are described as experimental and remain disabled by default (enabled by flags at runtime).
Another goal of Ruby 3.0 is to improve concurrency and two more utilities Fibre Scheduler, and experimental Ractor facilitate the goal. Ractor is light-weight and thread-safe as it is achieved by exchanging messages rather than shared objects.
Ruby 3.0 introduces RBS language to describe the types of Ruby programs for static analysis. It is separated from general Ruby programs.
There are some syntax enhancements and library changes in Ruby 3.0 as well.
Ruby 3.1 was released on 25 December 2021. It includes YJIT, a new, experimental, Just-In-Time Compiler developed by Shopify, to enhance the performance of real world business applications. A new debugger is also included. There are some syntax enhancements and other improvements in this release. Network libraries for FTP, SMTP, IMAP, and POP are moved from default gems to bundled gems.
Ruby 3.2 was released on 25 December 2022. It brings support for being run inside of a WebAssembly environment via a WASI interface. Regular expressions also receives some improvements, including a faster, memoized matching algorithm to protect against certain ReDoS attacks, and configurable timeouts for regular expression matching. Additional debugging and syntax features are also included in this release, which include syntax suggestion, as well as error highlighting. The MJIT compiler has been re-implemented as a standard library module, while the YJIT, a Rust-based JIT compiler now supports more architectures on Linux.
Ruby 3.3 was released on 25 December 2023. Ruby 3.3 introduces significant enhancements and performance improvements to the language. Key features include the introduction of the Prism parser for portable and maintainable parsing, the addition of the pure-Ruby JIT compiler RJIT, and major performance boosts in the YJIT compiler. Additionally, improvements in memory usage, the introduction of an M:N thread scheduler, and updates to the standard library contribute to a more efficient and developer-friendly Ruby ecosystem.
Ruby 3.4 was released on 25 December 2024. Ruby 3.4 adds it block parameter reference, changes Prism as default parser, adds Happy Eyeballs Version 2 support to socket library, improves YJIT, adds modular Garbage Collector and so on.


## Ruby 4
Ruby 4.0 was released 25 December 2025. It adds experimental ZJIT, a JIT written in Rust, and experimental "Ruby Box", a feature to provide separation about definitions. It was decided to bump the version number to 4.0 instead of 3.5 to celebrate Ruby's 30th birthday.


## Semantics and philosophy

Matsumoto stated that Ruby is designed for programmer productivity and fun, following the principles of good user interface design. At a Google Tech Talk in 2008 he said, "I hope to see Ruby help every programmer in the world to be productive, and to enjoy programming, and to be happy. That is the primary purpose of Ruby language." He stresses that systems design needs to emphasize human, rather than computer, needs:

Often people, especially computer engineers, focus on the machines. They think, "By doing this, the machine will run fast. By doing this, the machine will run more effectively. By doing this, the machine will something something something." They are focusing on machines. But in fact we need to focus on humans, on how humans care about doing programming or operating the application of the machines. We are the masters. They are the slaves.

Matsumoto has said his primary design goal was to make a language that he himself enjoyed using, by minimizing programmer work and possible confusion. He has said that he had not applied the principle of least astonishment (POLA) to the design of Ruby; in a May 2005 discussion on the newsgroup comp.lang.ruby, Matsumoto attempted to distance Ruby from POLA, explaining that because any design choice will be surprising to someone, he uses a personal standard in evaluating surprise. If that personal standard remains consistent, there would be few surprises for those familiar with the standard.
Matsumoto defined it this way in an interview:

Everyone has an individual background. Someone may come from Python, someone else may come from Perl, and they may be surprised by different aspects of the language. Then they come up to me and say, 'I was surprised by this feature of the language, so Ruby violates the principle of least surprise.' Wait. Wait. The principle of least surprise is not for you only. The principle of least surprise means principle of least my surprise. And it means the principle of least surprise after you learn Ruby very well. For example, I was a C++ programmer before I started designing Ruby. I programmed in C++ exclusively for two or three years. And after two years of C++ programming, it still surprises me.

Ruby is object-oriented: every value is an object, including classes and instances of types that many other languages designate as primitives (such as integers, Booleans, and "null"). Because everything in Ruby is an object, everything in Ruby has certain built-in abilities called methods. Every function is a method and methods are always called on an object. Methods defined at the top level scope become methods of the Object class. Since this class is an ancestor of every other class, such methods can be called on any object. They are also visible in all scopes, effectively serving as "global" procedures. Ruby supports inheritance with dynamic dispatch, mixins and singleton methods (belonging to, and defined for, a single instance rather than being defined on the class). Though Ruby does not support multiple inheritance, classes can import modules as mixins.
Ruby has been described as a multi-paradigm programming language: it allows procedural programming (defining functions/variables outside classes makes them part of the root, 'self' Object), with object orientation (everything is an object) or functional programming (it has anonymous functions, closures, and continuations; statements all have values, and functions return the last evaluation). It has support for introspection, reflective programming, metaprogramming, and interpreter-based threads. Ruby features dynamic typing, and supports parametric polymorphism.
According to the Ruby FAQ, the syntax is similar to Perl's and the semantics are similar to Smalltalk's, but the design philosophy differs greatly from Python's.


## Features
Thoroughly object-oriented with inheritance, mixins and metaclasses
Dynamic typing and duck typing
Everything is an expression (even statements) and everything is executed imperatively (even declarations)
Succinct and flexible syntax that minimizes syntactic noise and serves as a foundation for domain-specific languages
Dynamic reflection and alteration of objects to facilitate metaprogramming
Lexical closures, iterators and generators, with a block syntax
Literal notation for arrays, hashes, regular expressions and symbols
Embedding code in strings (interpolation)
Default arguments
Four levels of variable scope (global, class, instance, and loc