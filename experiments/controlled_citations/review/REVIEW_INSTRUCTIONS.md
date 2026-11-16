# Independent review instructions

These are constructed meeting-style snippets based on real legislative identifiers and titles. They are not quotations from real proceedings. Judge only the displayed snippet and candidate title; do not look up legislation or infer facts from external knowledge.

Complete your own CSV or TXT form independently. Do not inspect the other form, case metadata, source specifications, prompts, model outputs, or mapping files until your review is saved. Forms hide intended variant, split, original labels, and the other reviewer's responses. Similar examples can still be recognizable; blinding is procedural, not a security guarantee.

For each item fill every field except NOTES, which is optional:

- TOPIC_MATCH / topic_match: YES if the target measure is clearly mentioned; NO if the snippet only addresses a different measure; CANT_TELL if uncertain. Mentioning the target by identifier can establish this without establishing substantive support.
- CONTENT_SUPPORT / content_support: YES if substantive information about the target is consistent with its title; NO if there is no substantive information about the target or it conflicts; CANT_TELL if the text is ambiguous. Do not treat content explicitly attached to a different measure as evidence about the target.
- LABEL / label: SUPPORTED for a substantive description consistent with the title; CONTRADICTED for a substantive description attributed to the target that conflicts with the title; UNVERIFIABLE for insufficient or ambiguous target-specific description. A mere identifier, vote, or title readout is insufficient. This is an independent judgment, not an automatically derived label.
- NOTES / notes: briefly explain ambiguity, a contradiction, or concerns about the constructed example. Do not change the example text or its review ID.

Different amounts of detail can still count as support. Do not require a verbatim title match, and do not assume all items have an intended correct answer. Use CANT_TELL and UNVERIFIABLE when appropriate. Both reviewers must finish before comparisons or discussion. Preserve the original submitted forms unchanged; record any later adjudication separately before viewing model results.

Save a copy as `emma_completed.csv` / `vivianne_completed.csv` or corresponding `.txt`. The analysis accepts either format. Do not overwrite the distributed blank forms.
