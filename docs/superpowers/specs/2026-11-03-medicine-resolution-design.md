# Meal timing and context-aware medicine suggestions — design

**Date:** 3 November 2026. **Status:** approved by Aditya in chat, 3 Nov.
**Evidence:** Aditya's four browser recordings (encounters `enc-1610712bcb62`, `enc-fe188830854d` and two others).

## Problems seen

1. Meal instructions were quoted but never parsed. "before breakfast" and "once a day post-lunch" became
   `unparsed_food` warnings with empty food and timing, because the parser only knows "after food",
   "खाने के बाद" and similar, never breakfast, lunch or dinner.
2. Misheard brand names were never resolved. Speech-to-text wrote brand names that sound alike but are spelt
   differently (examples are kept in the private note, runbook Q-04). The matcher compares spellings with
   the 25-row formulary only and ignores what else was said ("antacid", "gas medicine", "for collagen",
   the knee ligament tear).

## A. Meal timing

- A meal phrase names a relation (before, after, with; pre-, post-; से पहले, के बाद, के साथ) and a
  meal (breakfast, lunch, dinner, supper; नाश्ता, दोपहर का खाना, रात का खाना; the English word inside
  Hindi codemix). It yields both a food rule and a slot: breakfast is morning, lunch afternoon,
  dinner and supper night.
- Combined with the timing phrase: no timing, or a daily frequency equal to the number of meals named,
  becomes a slot grid; a grid that names the same slots stands; a grid that contradicts the meals keeps
  the stated grid and leaves timing unresolved (a warning). As-needed and taper schedules are untouched.
- A missing dose still blocks: the doctor must say how many.

## C. Catalogue

- Two tiers. The reviewed formulary (`data/formulary/products.csv`) matches exactly and automatically,
  as now. Everything else is a suggestion the doctor confirms: the Indian Medicine Dataset
  (`public.indian_products`, unverified) and clinic products.
- Clinic products: a doctor can add a product while fixing a flag (brand, form, components). It is
  stored per organisation, pending review, and can be chosen at once. A hospital's pharmacy drug master
  can be imported into the same table later.
- A product chosen from either tier is frozen into the draft (`products_used`), as formulary products
  are, with an id that shows its tier (`in-…`, `cp-…`).

## B. Suggestions for a medicine that didn't match exactly

1. Candidates by sound and spelling over all tiers and the doctor's past choices: Indian-English sound
   swaps (m/p/b, k/c/q/g, t/d, s/z/j, v/w/f/ph), vowels and doubled letters folded; strengths must agree
   ("40" stays 40).
2. Context fit from the knowledge base: the sentence around the name, the visit's findings and the other
   medicines, compared with each candidate's uses, drug class and categories in `knowledge_chunks`.
3. Groq orders the top candidates with a one-line reason each. It may only return candidates it was
   given; the code checks every id. If Groq fails, the numeric order stands.
4. The doctor confirms with one click. Nothing is ever applied automatically: sound-alike pairs such as
   Pan 40 and Pan-D are where a confident wrong guess hurts (runbook D-92). The audit keeps what was
   heard and what was chosen.
5. Each confirmation is remembered per doctor (these heard words mean Pan 40) and ranks first next time, marked
   as the doctor's earlier choice. Still a suggestion.

## Unchanged rules

- The report never takes text from the knowledge base. Suggestions only propose which product was
  meant, and the doctor decides (D-99).
- Every suggestion shows its reason and its catalogue tier.

## Measures

A test set of real mishearings from the recordings above and earlier clips, plus sound-alike traps, kept
outside the repo (`../prisma-medicine-cases.json`): right product first, right product in the top three,
and a wrong product presented as the answer, which should stay near zero.
