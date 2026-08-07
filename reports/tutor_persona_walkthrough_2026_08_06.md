# Persona walkthrough — `tutor.html` ("the gardener"), 7 lessons

**Method:** three personas, built to spec, each taken through all 7 lessons of the live-shipped `tutor.html` (hosted at `https://rmichaelthomas.github.io/planes/tutor.html`, deployed via `.github/workflows/pages.yml`). This is a **virtual/textual cognitive walkthrough** — no browser was driven. Every claim below is grounded in the actual shipped source (`tutor.html`, `js/scene_vocab.mjs`, `index.html`, `README.md`) read directly, not inferred from the mockup or from memory of past checkpoints. Where a finding depends on exact copy, the source line is cited. No subagents were used — one pass, direct.

A visual/browser-driven version of this same exercise (real screenshots, real typing, real timing) is a natural follow-up if these findings earn it — flagged at the end, not assumed.

---

## 1. The personas

### Nadia, 12 — "burgeoning digital literacy, passive-constant access"

**Profile:** Has had a tablet/phone in reach since she could hold one. Fluent in *consuming* interfaces (YouTube, mobile games, group chats) but has rarely produced more than a text message or a Google Doc title. Has never used a raw text editor or seen a blinking cursor in an empty textarea. Typing speed is slow-ish and hunt-ish on a physical keyboard; touchscreens are her native input.

**Behaviors:** Trusts grey placeholder text to mean "type here." Reads the big picture (the canvas) before reading any paragraph. Treats a native browser popup (`confirm()`) as scary/adult — the kind of dialog that shows up before something breaks. Wants to see the picture change *immediately* after any action, or assumes she did it wrong. Motivated by finishing and by the certificate at the end more than by understanding.

**Goal here:** Finish something and get the certificate. Secondary goal: not feel dumb.

### Devon, 16 — "familiar with apps, not with code"

**Profile:** Comfortable with any app UI — settings menus, file upload, drag targets, form validation. Has done Scratch in middle school (blocks, not text) and nothing since. Judges new tools fast: gives a product about 90 seconds before deciding if it's "for me." Skims instructions, prefers to just click and see what happens, backfills understanding from the result.

**Behaviors:** Skips the lesson paragraph on first look, goes straight for Run. Notices UI inconsistencies (copy that doesn't match what's on screen) because comparing text-to-UI is a skill apps have trained into him. Compares everything mentally to Scratch and to whatever school coding unit he's had.

**Goal here:** Decide, in the first two lessons, whether this is "real coding" and whether it's worth his remaining attention.

### Priya, 38 — "career-transition adult, heard about Planes specifically"

**Profile:** Ten years in a non-technical field (operations/logistics), evaluating a move into tech. Came in through word of mouth about *Planes specifically* — the pitch that reached her was about a language that "shows its work" and can prove what a program can and can't do. Reads everything before acting — thorough, a little anxious about being behind, self-conscious about not being a "natural." Wants signal that this is a legitimate stepping stone, not just a kids' toy.

**Behaviors:** Reads every word of every lesson before touching the editor. Cross-references instructional copy against what's on screen (this trait is what surfaces the copy bug in §3.6). Pays close attention to anything that looks like a credential or a portfolio artifact. Mentally asks "would I put this on LinkedIn?" at the certificate.

**Goal here:** Decide if Planes — and self-taught learning in general — is a viable path into a tech career.

---

## 2. First contact, before lesson 1

`index.html`'s card copy for this page reads: *"Till your own garden, line by line — type a program, watch it grow, and click any part to ask where it came from. A hands-on path to a certificate."* The tab title is **"the gardener — till your own garden."**

- **Nadia** — the garden framing reads as "for me," warm and non-intimidating. No friction.
- **Devon** — clicks past the copy without reading it, same as any app-store description. No friction, but no persuasion either — he arrives with zero context on what he's about to do.
- **Priya** — friction here, mild but real (**P3**). She came in on Planes' pitch ("a language that shows its work," proof over trust) and lands on a page branded entirely around gardening, with no visible link back to that pitch. Her first reaction is *"did I click the wrong thing?"* She checks the header — "Planes" is there, small — and proceeds, but the identity gap costs a beat of hesitation before she's even typed anything.

---

## 3. Lesson-by-lesson

### 3.1 Lesson 1 — "place a thing"

Learner is told the first number in `sun of 240, 70` is **across**, the second is **down**, and to type the given 7 lines then press Run. The editor shows the target text as a full grey "ghost" — every keyword, every number — and typing directly overwrites it character by character; nothing is pre-typed for her.

- **Nadia** — this is the first time she's seen a real cursor-driven textarea. The type-over-ghost mechanic (trace the grey letters) is, in practice, forgiving — she can copy it almost mechanically. But nobody tells her *that's* what the grey text is for; the lesson paragraph never uses the word "ghost," "hint," or "grey." She works it out by trial in about 15–20 seconds of hesitation, then is fine. **P2** — first-contact affordance isn't explained, but it's guessable.
- **Devon** — types fast, doesn't read the paragraph, matches the grey text on instinct (same pattern as filling in a form with placeholder text). No friction. Hits Run, gets a picture. Mild positive surprise — "oh, that's satisfying."
- **Priya** — reads the paragraph fully first, then notices the editor already has grey text that matches what she just read. Slight redundancy but not a real problem — if anything it reinforces confidence. No friction.

**Cross-persona finding:** the ghost-text mechanic itself is a strong scaffold — everyone succeeds on the first try. The only real gap is that it's never *named* anywhere in the UI, so first-time-ever users (Nadia's case specifically) burn a few seconds confirming a guess rather than acting on a stated fact.

### 3.2 Lesson 2 — "across & down"

Place one bee, run it, then edit `300` → `400` and re-run to see it slide.

- **Nadia** — this is her favorite moment so far: change a number, watch the bee move. Immediate, causal, satisfying. No friction.
- **Devon** — same reaction, slightly more clinical: "OK, so numbers are positions." This is the moment he privately decides the tool is legitimate, not a toy — **this is his pass/fail gate**, and it passes.
- **Priya** — no friction; this is the first moment she feels the "shows its work" pitch showing up concretely (click a number, see cause and effect).

### 3.3 Lesson 3 — "day → night"

Parallel structure swap: sky phrase, ground stays, sun/bee become moon/firefly.

- All three — mechanically identical to lesson 1/2, no new friction for anyone. Devon explicitly notices the *parallelism* ("it's just the same shape with different words") and reads that as a positive sign of a well-designed teaching sequence.

### 3.4 Lesson 4 — "name it & why"

First abstraction: `let spot = 90 because "it's the tallest in the yard"`, then `two-flowers of 120, spot` — a name standing in for a number, plus a required, freeform justification string.

- **Nadia** — this is the first lesson where she has to understand something rather than transcribe it. She doesn't fully get *why* you'd name a number instead of just typing 90 directly — the lesson text doesn't explain the payoff (reuse, referencing it elsewhere, the click-to-ask card surfacing her own sentence back to her later). She gets it running by pattern-matching the ghost, but self-reports (see questionnaire) that she "didn't really get why you'd do that" until she later clicks the flower and sees her own sentence appear in the card. **P2** — the payoff of naming exists in the product (the reflection card literally quotes her `because` text back to her) but is one lesson removed from the lesson that introduces it, so the "aha" is delayed and easy to miss if she doesn't click.
- **Devon** — recognizes `let ... because` instantly as "basically a variable, but you also have to explain yourself." Mildly amused by the requirement to justify a number in words — flags it as the most "extra" part of the syntax so far, but not a blocker.
- **Priya** — this is her best moment. The forced `because` clause is exactly the "shows its work" promise made tangible at the smallest possible scale, and she says so unprompted in the questionnaire. No friction; this is the lesson that most converts her.

### 3.5 Lesson 5 — "two, their own height"

Two independent `let … because` pairs, encouraged to move only one.

- All three — a straightforward reinforcement lesson, no new concepts, no new friction. Devon and Priya both register it as "good spaced repetition"; Nadia doesn't notice it as a distinct step so much as "more of the flower thing," which is fine — nothing breaks.

### 3.6 Lesson 6 — "your own sky" (the confirmed copy bug)

This is the first lesson requiring the learner to **invent and consistently reuse her own name**, via a two-line pattern: a definition header and a matching call, e.g. `to your sky name here:` … later … `your sky name here`. A color-swatch panel writes the raw OKLCH numbers into a `custom-sky of …` line for her, so she never has to touch color math directly.

**Verified inconsistency, not a persona guess:** the lesson's own instructional text and the swatch panel's helper text both say to name the sky with **`to your words here:`** — but the actual line the learner needs to produce (and the only thing shown by the ghost text, which is authoritative because it's read straight from the `LESSONS` array that also drives execution) is **`to your sky name here:`**. Two different phrases, three vs. four words, sitting on screen at the same time:

- Lesson paragraph (`tutor.html:608`): *"Name it with **to your words here:**, then tap a color…"*
- Swatch panel help text (`tutor.html:371`): *"First name your sky with **to your words here:** on its own lines."*
- What the ghost text actually shows, character-for-character, because it's read from `LESSONS[5].lines` (`tutor.html:612` / `616`): **`to your sky name here:`** … **`your sky name here`**

Because the ghost is self-consistent (the header and the call agree with *each other*, just not with the prose describing them), nobody's program actually breaks if they type over the ghost as usual — the lessons before this one have trained everybody to do exactly that. The cost isn't a runtime error; it's a **stop-and-doubt moment** at the single highest-cognitive-load point in the whole tutorial (the first time anyone is asked to name something herself), right when confidence is most fragile.

- **Nadia** — doesn't read either paragraph closely enough to notice the mismatch; types over the ghost as always. Unaffected in practice, but this means the one persona who'd benefit most from confirming text matches editor is also the one least likely to catch a real bug like this in the wild.
- **Devon** — catches it. Reads the swatch panel (new UI, first time he's seen it, so he actually reads it this once), goes to type `to your words here:`, and the ghost in front of him is visibly different. Pauses, re-reads, decides to trust the editor over the paragraph. Costs him maybe 20–30 seconds and one "wait, is this broken?" moment. **P1** — this is exactly the kind of thing that makes an impatient-by-default user (§ persona pattern: skips docs, trusts the UI) suddenly *not* trust the UI.
- **Priya** — catches it immediately, being the most careful reader of the three. Unlike Devon she doesn't just shrug it off — she flags it explicitly in her questionnaire as "the moment I trusted this least." For a persona whose whole evaluation is "is this legit," a shipped copy/code mismatch on the *one lesson that's supposed to feel like real authorship* is disproportionately damaging to trust. **P1**, arguably **P0** for this specific persona's goal (assessing legitimacy).

The swatch color picker itself (tap a swatch, it writes `custom-sky of 0.78, 0.14, 55` at the cursor) is universally well-liked — nobody has to understand OKLCH to use it, and Devon in particular likes that "it does the math for you." If the "why" card is opened on a custom-sky mark, the three raw numbers are labeled "lightness," "richness," "hue" — "richness" as a stand-in for chroma is mildly opaque to Nadia and Devon but neither of them opens that card on this lesson unprompted.

### 3.7 Lesson 7 — "it's yours now" (capstone + certificate)

Combines everything, then surfaces three capstone cards ("your garden is honest," "share your garden," "keep growing it") plus a certificate flow (type a name, or don't; see a certificate; print it).

**Honest-garden card:** derived live from `analyseProgramGraph`, not a canned string — genuinely reads as a proof, not a marketing claim. All three personas find this credible; Priya explicitly likes that it's computed from her own program, not asserted.

**Share-your-garden card:** a random 6-digit "seed," a save-file button, an open-file button, and this line: *"Your teacher can call out these seeds at the front of the room — everyone's garden, one by one."*

- **Nadia** — this reads as completely normal; she assumes there *is* a classroom context even doing this solo, and it doesn't bother her.
- **Devon** — neutral; he's plausibly in an actual classroom, so the line lands fine.
- **Priya** — this is the moment the identity gap from §2 resurfaces and sharpens. She has no teacher. Doing this alone, at her kitchen table, evaluating a career change, being told her "seed" is for a teacher to call out "at the front of the room" is a small but pointed *this wasn't built for someone like me* signal, arriving right at the finish line. **P2** — not a blocker, but it undercuts the exact moment the product most wants to feel earned.

**No autosave, anywhere.** The product deliberately has no localStorage — the save-file/open-file pair *is* the persistence model (confirmed in source comments). The only warning of data loss is a native `window.confirm()` popup, and only when switching lessons with unsaved text — there's no `beforeunload` guard, so a refresh, an accidental back-swipe, or a closed tab loses everything silently, with zero warning.

- **Nadia** — highest risk here. She's the persona least likely to think "I should save a file" as a mental model (her lived experience is apps that autosave everything, always) and most likely to be interrupted mid-session (phone call, sibling, class bell) and lose work with no signal anything was lost. **P1.**
- **Devon** — mid risk; app-conditioned like Nadia, but more likely to notice a save/download button and use it once he sees it, since "download the file" is a familiar app pattern to him.
- **Priya** — lowest risk; explicitly notices and uses "save my garden file" without prompting, treating it the way she'd treat any local document.

**Certificate:** name field (optional, defaults to "a Planes gardener" if left blank), a full-screen certificate with a rainbow-gradient band and four colored "chips" ("wrote a program," "named the numbers," "said why," "made it their own"), and one real action — **Print it** (`window.print()`).

- **Nadia** — delighted. This is her peak moment (see questionnaire) — the visual payoff matches the effort. No friction.
- **Devon** — likes it, mildly disappointed there's no direct "save as image" or share button — a generation raised on Duolingo streaks and shareable achievement cards expects a one-tap share, not a print dialog. **P3.**
- **Priya** — this is where the "toy vs. credential" tension peaks. The certificate is warm and well-crafted, but nothing about it is built to leave the product — no PDF export, no shareable link, no LinkedIn-shaped artifact, and the only exit is a browser print dialog she has to know to redirect to "Save as PDF" herself. For the one persona actually evaluating whether to invest further, the capstone artifact that's supposed to be evidence of the work has no path off the page. **P2.**

---

## 4. Exit questionnaire

*(identical instrument given to all three, as if delivered as a short post-lesson form)*

| # | Question | Nadia, 12 | Devon, 16 | Priya, 38 |
|---|---|---|---|---|
| 1 | Overall clarity (1–5) | 4 | 4 | 4 |
| 2 | Confidence before → after (1–5 each) | 2 → 4 | 3 → 4 | 2 → 4 |
| 3 | Most confusing moment | "The grey letters at the very start — I didn't know if I was supposed to erase them or type over them." | "Lesson 6 — the instructions said one thing and the box said another. I went with the box." | "Lesson 6, same thing Devon flagged — that's the one time I didn't fully trust what I was reading." |
| 4 | Proudest / favorite moment | "Getting my certificate at the end — I want to show my mom." | "Moving the bee and watching it actually slide — that's when I stopped thinking it was fake." | "Writing my own `because` — that's the first time it felt like *my* reasoning was actually part of the program, not just decoration." |
| 5 | Did this feel like "real" programming? | "I don't know, but it felt like *making* something." | "More real than Scratch, less real than what my cousin does at his internship — probably somewhere in between." | "Yes, more than I expected — but the ending (garden/teacher framing, no way to export the certificate) made me doubt whether this is *for* someone in my position." |
| 6 | Continue on your own? | Yes — "if my friend does it too." | Maybe — "depends if there's a next thing after this." | Yes, tentatively — "I'd want to see what comes after the certificate before deciding this is a real path." |
| 7 | Recommend to a peer in your position? | Yes | Yes, with "it's more typing than Scratch, heads up" | Yes, with a caveat: "tell them lesson 6's instructions have a typo, don't let it shake their confidence." |
| 8 | One change you'd make | "Tell me what the grey letters mean before lesson 1." | "Fix lesson 6's text, and let me share the certificate somewhere, not just print it." | "Either drop the classroom language in the final lesson or add an adult/self-directed variant — and please fix the lesson 6 mismatch, it's a trust issue." |

---

## 5. What's working (don't lose this in a fix pass)

1. **Type-over-ghost is a genuinely strong onboarding mechanic.** All three personas complete every lesson on or near the first attempt because the exact target text is always visible and forgiving to approximate. This is doing more first-contact work than the lesson prose is.
2. **Error copy is already good.** `friendlyError()` (`tutor.html:918-945`) deliberately avoids raw parser tags and points learners at the key panel by name instead of dumping a stack-shaped message — this didn't surface as a friction point for any persona because it's already been designed against exactly this kind of confusion.
3. **The honest-garden capstone card is computed, not asserted** — it's the single strongest trust-building moment in the whole flow, and it's the one moment all three personas independently praised without prompting.

## 6. Prioritized findings

| Sev | Finding | Who it hits hardest | Fix |
|---|---|---|---|
| **P1** | Lesson 6 instructional copy ("`to your words here:`" — lesson text `tutor.html:608` and swatch help `tutor.html:371`) doesn't match the actual required text ("`to your sky name here:`" — `tutor.html:612`/`616`, the ghost's own source). | Devon, Priya (careful/comparative readers); latent risk for anyone who reads before typing | One-line copy fix — align both prose strings to the real target text. Cheapest, highest-confidence fix in this report. |
| **P1** | No `beforeunload` guard and no autosave — a refresh, closed tab, or interruption loses all typed work silently, with zero warning outside the lesson-switch confirm. | Nadia (app-conditioned to expect autosave, likely to be interrupted) | Add a `beforeunload` prompt when `source.value` is non-trivial and unsaved; consider a lightweight "you have unsaved work" indicator near Run. |
| **P2** | The ghost-text mechanic is never named or explained anywhere in the UI or lesson 1 copy. | Nadia (first-ever raw-editor experience) | One sentence in lesson 1's `lesson` text: something like "the grey letters show you what to type — write right over them." |
| **P2** | Capstone's classroom-only framing ("your teacher can call out these seeds…") has no self-directed-adult equivalent, landing at the exact moment a career-evaluating adult is deciding whether this product is "for" them. | Priya | Either broaden the copy to cover solo/self-directed use, or branch the capstone card's language on some lightweight context signal. |
| **P2** | Certificate's only export path is a browser print dialog — no image/PDF/share affordance. | Priya (portfolio value), Devon (share-culture expectation) | Add a "save as image" (canvas-to-PNG, same pipeline the picture export already uses) alongside Print. |
| **P3** | Lesson 4 introduces `let … because` without stating the payoff (that the sentence resurfaces later in the click-to-ask card); the payoff is discovered only if the learner clicks a mark. | Nadia | Add a half-sentence forward-reference in lesson 4: "click the flower later and you'll see this sentence again." |
| **P3** | "the gardener" branding on the landing card gives no visible bridge back to Planes' core "shows its work" pitch for someone arriving from that pitch specifically. | Priya | Minor — a sub-line under the tab title/header tying the garden framing back to the proof-based pitch would close the gap in one line. |

## 7. Where the personas genuinely disagree

Not every finding above is a shared complaint — a few are direct **tensions**, where a fix for one persona actively costs another:

- **Garden/nature framing and classroom language** (bee, flower, "your teacher can call out these seeds") is exactly right for Nadia and neutral-to-fine for Devon, but is the single biggest credibility cost for Priya. A blanket rewrite toward "more serious/professional" tone would likely *reduce* Nadia's completion rate and enjoyment, not just fix Priya's trust gap. This argues for a branch or a lightweight audience toggle, not a uniform copy change.
- **Certificate as pure delight vs. certificate as evidence** — Nadia's peak moment is Priya's biggest letdown, from the identical screen. The fix for Priya (export/share affordances) costs nothing for Nadia and can be purely additive.

---

## 8. Suggested next step

This pass is entirely textual, grounded in the shipped source but not in an actual rendered browser — no real typing speed, no real layout/viewport behavior (mobile especially, given Nadia and Devon's device habits), no real screenshots. If these findings are worth acting on, the natural next step you flagged is a **visual pass**: drive an actual browser (Playwright) through the same three personas' same 7 lessons, on both desktop and a phone-sized viewport, and capture what actually renders — that would confirm or correct anything here that depends on real screen space, real typing friction, or real timing, and would catch the lesson-6 copy bug on-screen rather than in source. Say the word and I'll run that next; not started here.

Rob's read after living through this himself: agrees with the findings above. One flagged methodology note for next time — mixing the two youngest personas (Nadia, Devon) with the career-transition adult (Priya) in a single run produced some real, useful tension callouts (§7) but may have been the wrong grouping to run together; a future pass might separate the school-age cohort from the self-directed-adult cohort so each gets a cleaner read, or keep them mixed deliberately when the *tension itself* is the thing being tested.

## 9. Resolved — 2026-08-06

All findings above accepted; fixes applied directly to `tutor.html` in this pass. No visual/browser pass run (declined — findings were confirmed by Rob's own hands-on use).

| Finding | Status | What changed |
|---|---|---|
| Lesson 6 copy mismatch (`to your words here:` vs `to your sky name here:`) | **Fixed** | Both the lesson-6 `lesson` text and the swatch-panel help paragraph now say `to your sky name here:`, matching the ghost text and the actual required line. |
| No `beforeunload` guard | **Fixed** | Added — prompts before leaving the page (refresh, close, back) whenever the editor holds unsaved text. Doesn't track save-state precisely (warns even right after a save, matching the existing lesson-switch confirm's same simple non-empty check) — acceptable trade-off, not a precise dirty-flag. |
| Ghost-text mechanic never explained | **Fixed** | Lesson 1 now opens with "The grey letters below are what to type — write right over them, and they'll clear as you go." before the original instructions. |
| Lesson 4's `because` payoff not forward-referenced | **Fixed** | Added "Click the flower after you run it — your reason shows up right there." to the lesson-4 text. |
| Classroom-only capstone framing | **Fixed, per explicit instruction** | "Your teacher can call out these seeds at the front of the room…" replaced with "Trade seeds with anyone else growing a garden — the same seed always grows the exact same one." — same seed-sharing mechanic, no assumed setting. |
| Certificate has no export path beyond Print | **Partially addressed** | Added a one-line hint ("Choose 'Save as PDF' instead of a printer…") rather than building true image/PDF export — the certificate is a styled DOM node, not the canvas the picture's PNG export already pipelines from, so a real export feature is a larger build than this pass's scope. Flagged as a real follow-up if it matters enough to build. |
| Landing-page identity bridge (`index.html` card copy vs. Planes' core "shows its work" pitch) | **Deferred, not done** | Lower priority (P3), and the header tagline this would touch is shared verbatim across every page on the site — higher blast radius than this pass's scope justified without a separate look at site-wide copy. |

Verification: `node --test js/test/*.test.mjs` — 805/805 passing after the edits (including all 14 in `js/test/tutor_redesign.test.mjs`, which exercises the ghost-text mechanism directly).
