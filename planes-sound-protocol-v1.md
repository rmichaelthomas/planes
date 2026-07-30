# The Planes Sound Protocol

**Version 1**

A Planes program cannot make a sound. It can emit text. This document defines a
text format that a program emits and a player consumes, so that one program can
be played by many players without the program knowing which — or knowing that
anything is listening at all.

The program's effect surface is `console` for every player, because emitting
these lines is emitting text and nothing else.

This is the drawing protocol's architecture, deliberately: a prefix that cannot
collide with prose, a version declaration that must precede the first sounding
command, a refusal contract, a fixed-arity verb table, and one shared walk with
more than one sink behind it. Where a rule here matches
`planes-drawing-protocol-v2.md`, it matches on purpose and says so.

---

## 1. The stream

A player consumes a sequence of lines, in order. Each line is either a
**command** or **prose**.

A command begins with the word `sound`, followed by a verb, followed by that
verb's arguments, separated by one or more spaces.

```
sound note 3 2 1 0.5 0.4
```

Any line not beginning with `sound` is prose. The player does not interpret it
and passes it to whatever text surface it has. Prose may contain any words at
all, including verb names.

A stream may carry **both** protocols at once. `draw` lines are prose to a
player and `sound` lines are prose to a renderer, and neither has to know the
other exists — which is the whole reason both use a prefix.

### 1.1 The version declaration

```
sound protocol 1
```

A stream may declare the protocol version it is written against. If present,
the declaration **must appear before the first sounding command**. A player
cannot refuse a phrase it has already begun playing.

- If absent, the version is 1.
- A second declaration in one stream, or one appearing after a sounding
  command, is an error.
- A player that does not implement the declared version **refuses the entire
  stream** and reports why. It does not play the commands it recognises and
  discard the rest. A half-played phrase with no error is the failure this
  declaration exists to prevent.

`protocol` is not a sounding command and changes nothing about what is heard.

---

## 2. The refusal contract

A line beginning with `sound` **is** a command. It is never reinterpreted as
prose.

The following are errors, reported with the offending line:

- an unrecognised verb
- the wrong number of arguments for a verb
- an argument that is not a valid number where a number is required
- a word argument outside its permitted set
- a version declared that this player does not implement

And, because a ratio and a schedule can be well-formed and still meaningless:

- a ratio with a denominator of zero, or with a non-positive numerator
- a `gain` outside 0 to 1
- a note starting before the tick does, or lasting no time at all

A player reports the error rather than playing a partial phrase in silence.

---

## 3. Time and numbers

- Times are in **seconds**, relative to the start of the tick that emitted the
  stream.
- A number is an optional `-`, then digits, optionally a `.` and more digits.
  No exponent notation.
- A number may carry a leading `~`. This is how Planes renders a rational whose
  decimal expansion does not terminate. The player **accepts and discards** the
  `~`; it is never part of the value.

### 3.1 A schedule, not a stream of live events

A Planes program runs start to finish and cannot be called back part way
through. It therefore emits a **schedule**: every note says when it starts and
how long it lasts, and the player is responsible for making that happen.

A player receiving a stream at wall-clock time `T0` plays a note whose `at` is
`a` at `T0 + a`. **Notes whose time has already passed are dropped** — a player
that has spent 40 milliseconds walking a stream does not race to catch up on a
note scheduled for millisecond 10; it drops it and says nothing. Dropping is
the specified behaviour, not a failure.

This is the sound counterpart of the drawing protocol's §8.1: *playing gives
you what the program said, when the program said it happens.*

---

## 4. Pitch

Pitch is a **ratio**, always, everywhere in this protocol. There is no second
pitch model and no alternative spelling. A note names a numerator, a
denominator, and an octave.

```
sound note 3 2 1 0.5 0.4
```

— a perfect fifth (3/2) above the base, one octave up, starting half a second
into the tick, lasting four tenths of a second.

The frequency a player sounds is

```
base × 2^octave × numerator / denominator
```

with **base = 220 Hz**, pinned here so that two players cannot disagree about
what a stream means. `octave` is an exponent, not a multiplier: `0` is the base
octave, `1` is one octave up, `-1` one octave down.

### 4.1 Why a ratio

Just intonation is expressible exactly in this language and equal temperament
is not. A perfect fifth is 3/2 and stays 3/2 forever; the twelfth root of two
is not a rational and never will be. A protocol that carried a frequency would
force every program to round before it spoke, and the rounding would be the
first thing a `why` chain reached.

| Ratio | Interval |
|---|---|
| 1/1 | unison |
| 9/8 | whole tone |
| 6/5 | minor third |
| 5/4 | major third |
| 4/3 | fourth |
| 3/2 | fifth |
| 5/3 | major sixth |
| 2/1 | octave |

Three notes that belong together, computed rather than looked up, and traceable
through `why` like any other derivation — exactly the argument
`planes-drawing-protocol-v2.md` §4.1 makes for hue in degrees.

### 4.2 Stated limit: a ratio a player cannot resolve is still played

A denominator large enough to put a note above the sample rate's Nyquist limit,
or below what a speaker can move, is not refused. It is played, and what comes
out is silence or an alias. This is a real limit of digital audio meeting a real
limit of hardware, and it is stated here rather than discovered — the same
shape as the drawing protocol's silent gamut clamp (§4.2 there).

---

## 5. Initial state

At the start of every stream, a player resets to:

| | |
|---|---|
| wave | `sine` |
| gain | `0.2` |
| schedule | empty |

Nothing persists between streams except what the program restates. A Planes
program holds no state; the page may. The player's state is per-stream and
begins from this table every time.

---

## 6. The verbs

Four. Every one plays natively both through a live audio graph and into a
sample buffer written to a file, with no translation layer on either side.

### 6.1 Voice

| Verb | Arguments | |
|---|---|---|
| `wave` | `sine` \| `triangle` \| `square` | the waveform notes are sounded with |
| `gain` | g | peak amplitude, `0` to `1` |

Both are state, exactly like the drawing protocol's `stroke` and `width`: they
apply to every note emitted after them, until changed.

`gain` is the note's own peak, before the player's master level. Two notes at
`gain 0.5` overlapping are two notes at half amplitude, not one — a program
that wants a phrase to swell as a unit writes the swell into its own gains.

### 6.2 Notes

| Verb | Arguments | |
|---|---|---|
| `note` | numerator denominator octave at lasts | one note, scheduled |
| `silence` | — | discard every note scheduled so far in this stream |

`numerator` and `denominator` are the pitch ratio (§4). `octave` is an integer
exponent of two. `at` is when the note starts, in seconds from the start of the
tick; `lasts` is how long it sounds, in seconds.

`lasts` is spelled `lasts` rather than `for` because `for` is a reserved word in
Planes and a helper parameter cannot be named it. The protocol and its Planes
helper library use the same words, so a collision in one renames both — the
rule `planes-drawing-protocol-v2.md` §6.5 states for `label` and `corner`, met
again here.

`silence` is spelled `silence` rather than `clear` for the same reason, one
level further out: `clear` is already a verb of the drawing protocol, and
`paint/draw.planes` already defines a helper called `clear`. A program that
emits both protocols — which is the whole point of the prefix — imports both
libraries into one module graph, and two helpers of one name is a collision the
loader refuses. The word that had to move is the newer one.

---

## 7. The envelope, pinned

Two players will disagree about what a note sounds like unless this is exact.

- A note rises linearly from silence to its `gain` over the first **0.16
  seconds**, or over `lasts`, whichever is shorter.
- It then falls exponentially to 0.0001 of full scale at exactly `lasts`.
- It is silent before `at` and after `at + lasts`.

This is one formula, held in the shared walk, so a player that schedules ramps
on an audio graph and a player that computes samples one at a time are given
the same curve rather than each choosing one.

---

## 8. Player conformance

A player implements a whole version or refuses it. There is no partial
conformance and no verb-by-verb negotiation, because a program that cannot know
what is listening cannot adapt to a player's gaps.

A player states, in its own documentation, which versions it implements.

A player whose medium cannot express a verb states that as a documented
limitation of that player. It does not silently skip commands.

### 8.1 Two players, deliberately

This repository ships two: a live one over Web Audio (`js/sound/audio.mjs`) and
one that writes a `.wav` file (`js/sound/wav.mjs`). The reason is the reason the
drawing protocol has canvas and SVG — with one player, semantics leak into it
and the shared walk stops being normative, and nobody finds out until the second
one is written. The file writer also gives a phrase you can keep.

---

## 9. Known limits of version 1

- **No live input.** A program emits a schedule and cannot be called back part
  way through it (§3.1). This is a property of the language, not a gap.
- **No polyphonic voice control.** Every note carries its own wave and gain from
  the state at the moment it was emitted; there is no voice, channel or bus.
- **No stereo.** One channel. A pan argument would double the verb table's
  numeric arguments for something neither player needs yet.
- **No effects.** No reverb, no filter, no delay. A filter would have to be
  specified precisely enough that a sample-accurate writer and a browser audio
  graph produced the same sound, which is a larger question than a verb table
  entry.
- **The wave set is closed at three, and stays closed.** `sine`, `triangle` and
  `square` are exactly reproducible from a formula in both media. A sawtooth
  would be too; anything band-limited would not be, and the two players would
  diverge on the harmonics — the same argument `blend`'s closed mode set makes
  in the drawing protocol.

---

## 10. Writing this from Planes

Emitting these lines by hand is string assembly:

```
show "sound note " + text of n + " " + text of d + " " + text of octave + " " + text of at + " " + text of lasts
```

The companion library `sound.planes` wraps every verb once so that programs do
not:

```
use sound
note of 3, 2, 1, 0.5, 0.4
```

The library holds **one helper per verb in this document, and nothing else**.
The specification and the library are the same thing written twice, and that
correspondence is mechanically checkable — `js/test/sound_library.test.mjs`
reads the verb table straight out of `js/sound/protocol.mjs` and asserts it.

---

*Version 1. This document defines the format; a player implements it; a program
emits it and knows about none of them.*
