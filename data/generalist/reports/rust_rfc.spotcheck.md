# rust_rfc: 20 random items for a spot check

Check the gold label against the linked source record.

## 1. rust-lang/rfcs#1361 (train): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/1361

```
Rust RFC pull request (opened 2015-11-10)
Title: RFC: Improve Cargo target-specific dependencies
Description: Improve the target-specific dependency experience in Cargo by leveraging the same `#[cfg]` syntax that Rust has.

Where did this RFC pull request end up?
```

## 2. rust-lang/rfcs#3935 (train): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/3935

```
Rust RFC pull request (opened 2026-03-25)
Title: initial draft for 2026 project goals
Description: Establish the initial round of Rust Project Goals for 2026 along with a set of current roadmaps, which describe multi-year development arcs. New Rust Project Goals may be added over the course of the year but only if all required resources (champions, funding, etc) are already known.

What was the outcome of this RFC pull request?
```

## 3. rust-lang/rfcs#3184 (train): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/3184

```
Rust RFC pull request (opened 2021-10-17)
Title: Thread local Cell methods.
Description: This is a relatively small RFC. But I figured it'd be nice to discuss the API and alternatives here where it gets a bit more attention. (And without getting distracted by the implementation details of `.set()`.).

What was the outcome of this RFC pull request?
```

## 4. rust-lang/rfcs#2364 (train): gold = Postponed: closed for now, to be revisited later

https://github.com/rust-lang/rfcs/pull/2364

```
Rust RFC pull request (opened 2018-03-19)
Title: Add RFC: formalise reborrows
Description: Summary: Formalise the re-borrowing logic used on `&T` and `&mut T`. Motivation: Solve Some way to simulate `&mut` reborrows in user code.

How did this RFC pull request end?
```

## 5. rust-lang/rfcs#3627 (test): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/3627

```
Rust RFC pull request (opened 2024-05-06)
Title: Match ergonomics 2024
Description: Changes to match ergonomics for the 2024 edition. [user] label T-lang A-patterns A-edition-2024. Tracking:

What was the outcome of this RFC pull request?
```

## 6. rust-lang/rfcs#2874 (test): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/2874

```
Rust RFC pull request (opened 2020-03-04)
Title: Added RFC for trait enums
Description: This is an RFC to add safe unions which can be used as conveniently as trait objects.

Where did this RFC pull request end up?
```

## 7. rust-lang/rfcs#3456 (train): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/3456

```
Rust RFC pull request (opened 2023-07-10)
Title: Add `bf16`, `f64f64` and `f80` types
Description: Previous RFC #3451 mixes proposal for IEEE-754 compliant `f16`/`f128` and such non-standard types, split this off from it to focus on the target related ones.

What was the outcome of this RFC pull request?
```

## 8. rust-lang/rfcs#3537 (test): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/3537

```
Rust RFC pull request (opened 2023-11-29)
Title: RFC: Make Cargo respect minimum supported Rust version (MSRV) when selecting dependencies
Description: If the proposed resolver solution is still not to your liking, I would recommend focusing the discussion on (in priority order): Whether there are disagreements on the core principles. If agreement above, whether there is disagreement with the evaluation of the workflows based on the above principles. If agreement above, whether there is disagreement with the workflow prioritization based on the above evaluation. If agreement above, whether there is disagreement with the evaluation of the solutions impact on the workflows, based on the principles. If agreement above, whether there is disagreement with the selected solution based on the evaluation. In some cases, there is a need for a lot of digging in to understand concerns and use cases. Asynchronous back and forth can be wearing. I do host Office Hours for some synchronous communication. If none of those times work, feel free to reach out to me on Zulip to see if we can find another time.

Where did this RFC pull request end up?
```

## 9. rust-lang/rfcs#76 (train): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/76

```
Rust RFC pull request (opened 2014-05-14)
Title: Added RFC for multiple trait implementations for a single impl block
Description: This pull request will allow the following syntax: As said in the reddit thread, this RFC wold probably be a post 1.0 thing, but I wanted to get conversation started for this. Also I would not be able to implement this, I would love to be able to, but the knowledge is not in my brain! Any feedback? Would love to read more.

How did this RFC pull request end?
```

## 10. rust-lang/rfcs#3887 (train): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/3887

```
Rust RFC pull request (opened 2025-11-26)
Title: Create 0000-pub_use_pub_glob.md
Description: This RFC would introduce glob exports for only public item.

Which of these describes what happened to this RFC pull request?
```

## 11. rust-lang/rfcs#2196 (train): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/2196

```
Rust RFC pull request (opened 2017-10-31)
Title: metabuild: semantic build scripts for Cargo
Description: Introduce a mechanism for Cargo crates to make use of declarative build scripts, obtained from one or more of their dependencies rather than via a `build.rs` file. This allows us to experimentat with declarative build scripts in the crates.io ecosystem. With this mechanism, crates can specify `metabuild = ["somecrate", "anothercrate"]` in their `Cargo.toml`, and they'll automatically end up with a build script that invokes `somecrate::metabuild()` and `anothercrate::metabuild()`. Likely providers of crates for use with metabuild would include pkg-config (and more general native-library finders), parser generators, binding generators, other code generators, and anything else that would ordinarily say "add this to your `build.rs`" in its README.

Which of these describes what happened to this RFC pull request?
```

## 12. rust-lang/rfcs#3271 (train): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/3271

```
Rust RFC pull request (opened 2022-05-23)
Title: RFC: Add more support for fallible allocations in Vec
Description: `Vec` has many methods that may allocate memory (to expand the underlying storage, or shrink it down). Currently each of these method rely on "infallible" allocation, that is any failure to allocate will call the global OOM handler, which will (typically) panic. Even if the global OOM handler does not panic, the return type of these method don't provide a way to indicate the failure. Currently `Vec` does have a `try_reserve` method that uses "fallible" allocation: if `try_reserve` attempts to allocate, and that allocation fails, then the return value of `try_reserve` will indicate that there was a failure, and the `Vec` is left unchanged (i.e., in a valid, usable state). We propose adding more of these `try_` methods to `Vec`, specifically for any method that can allocate.

What became of this RFC pull request?
```

## 13. rust-lang/rfcs#160 (train): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/160

```
Rust RFC pull request (opened 2014-07-09)
Title: RFC for `if let` expression
Description: Start Date: (fill me in with today's date, YYYY-MM-DD). Introduce a new `if let PAT = EXPR { BODY }` construct. This allows for refutable pattern matching without the syntactic and semantic overhead of a full `match`, and without the corresponding extra rightward drift. Informally this is known as an "if-let statement". Many times in the past, people have proposed various mechanisms for doing a refutable let-binding. None of them went anywhere, largely because the syntax wasn't great, or because the suggestion introduced runtime failure if the pattern match failed. This proposal ties the refutable pattern match to the pre-existing conditional construct (i.e. `if` statement), which provides a clear and intuitive explanation for why refutable patterns are allowed here (as opposed to a `let` statement which disallows them) and how to behave if the pattern doesn't match.

What became of this RFC pull request?
```

## 14. rust-lang/rfcs#3307 (train): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/3307

```
Rust RFC pull request (opened 2022-08-28)
Title: De-RFC: Remove type ascription
Description: From the community that brought you the Pre-RFC and the e-RFC, we now introduce: the de-RFC! This RFC intends to advocate for the feature being removed entirely (or at least moving the implementation to a less prime area of the syntactic space) with a fresh RFC being necessary to add it again (which this RFC encourages the community to do!). (While I've taken some ... liberties with the RFC template here; it is not a joke; it's a serious attempt to give us a clean slate when it comes to this feature.).

Where did this RFC pull request end up?
```

## 15. rust-lang/rfcs#1954 (train): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/1954

```
Rust RFC pull request (opened 2017-03-18)
Title: Provide a more explicit way to "clone" a standard reference counted pointer.
Description: This is my first RFC. This RFC proposes a very small addition to the standard reference counted pointer types, that aims solving a recurrent paper-cut-type of annoyance related the lack of clarity of code calling ```clone()```.

Where did this RFC pull request end up?
```

## 16. rust-lang/rfcs#494 (train): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/494

```
Rust RFC pull request (opened 2014-11-30)
Title: RFC: Stabilize std::{c_str, c_vec}
Description: Stabilize the `std::{c_str, c_vec}` modules by re-working their interfaces and refocusing each primitive for one particular task. The three broad categories of interoperating with C will work via: If you have a Rust string/byte slice which needs to be given to C, then the `CString` type will be used to statically guarantee that a terminating nul character and no interior nuls exist. If C hands you a string which you want to inspect, but not own, then a helper function will assist in converting the C string to a byte slice. If C hands you a string which you want to inspect and own, then a helper type will consume ownership and will act as a `Box ` in essence.

How did this RFC pull request end?
```

## 17. rust-lang/rfcs#3168 (train): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/3168

```
Rust RFC pull request (opened 2021-08-24)
Title: Cargo allow running binaries from development or build dependencies
Description: In addition to binaries from workspace members, teach `cargo run` to execute binaries from dependent packages.

How did this RFC pull request end?
```

## 18. rust-lang/rfcs#1773 (train): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/1773

```
Rust RFC pull request (opened 2016-10-20)
Title: A type representing an owned C-compatible wide string
Description: This RFC born from issue: rust-lang/rust#36671. Add CWideString/CWideStr for more simple interaction with not well-formed UTF-16 external API (for example: with Windows API).

What became of this RFC pull request?
```

## 19. rust-lang/rfcs#3918 (train): gold = Closed without being merged

https://github.com/rust-lang/rfcs/pull/3918

```
Rust RFC pull request (opened 2026-02-10)
Title: RFC: Add `MaybeDropped `
Description: Adds a type for representing values whose destructor may have ran already.

How did this RFC pull request end?
```

## 20. rust-lang/rfcs#461 (train): gold = Merged: the RFC was accepted

https://github.com/rust-lang/rfcs/pull/461

```
Rust RFC pull request (opened 2014-11-11)
Title: RFC: Add a thread local storage module, std::tls
Description: Introduce a new thread local storage module to the standard library, `std::tls`, providing: Scoped TLS, a non-owning variant of TLS for any value. Owning TLS, an owning, dynamically initialized, dynamically destructed variant, similar to `std::local_data` today.

What became of this RFC pull request?
```

