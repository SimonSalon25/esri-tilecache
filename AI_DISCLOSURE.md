# Use of generative AI

This project was developed with a generative AI assistant. We state this openly because the way the work was done
is itself one of the results we want to share (see the planned paper on AI-assisted development in GIS).

## Tools

| tool | where |
|---|---|
| Claude (Anthropic) in the claude.ai agent workspace; model **Claude Opus 5.5** for this package (November 2026) | code, tests, documentation, this file |
| Claude models in earlier sessions of the parent application *Lesná mapa* (2026; exact model versions per session were not recorded) | the original Slovak implementation from which this package was translated |

## Division of work

**Author (human), Šimon Saloň:**
- defined the problem (the national map that GDAL could not open) and every requirement;
- made the decisions recorded in the project log (e.g. keep tiles byte for byte, convert `.vtpk` to MBTiles,
  store elevation as a gridded coverage, test on Esri's samples, MIT licence);
- tested each version on real national data on his own computer and reported the results and failures that led
  to fixes (for example the "database is locked" failure on Windows and the misplaced tiles caused by the ZIP
  reading problem);
- did not review the code line by line. He reviewed its behaviour: he read the decision log and the test descriptions for each change, ran every version on his own national data on his own computer (Windows) and in QGIS, reported failures, and accepted a change only after the full test suite and the mutation check passed. The authors take responsibility for the published code.

**Co-authors (humans):** Milan Koreň, František Chudý, Julián Tomaštík and Miroslav Kardoš (Department of Forest Resource Planning and Informatics, Technical University in Zvolen) work in GIS and forest mapping. In consultations with them the practical problems were identified that this work then solved with the AI assistant.

**AI assistant:**
- wrote the code, the tests and the documentation;
- analysed the Compact V1 layout on the national cache and the failures reported by the author;
- proposed options for decisions; the author chose.

## How AI output was checked

Nothing is accepted because the AI says it works. Every change in the parent project carries a numbered entry in
a decision log, a test, and a **mutation check**: the fix is deliberately broken and the test must fail. The full
test suite of the parent application (≈ 300 tests) runs before every release. Results on real data are measured
on the author's computer. Known AI mistakes caught by this process are documented in the project log (for example
mis-identified EPSG transformation codes and "caught" mutations that were in fact not caught); they are part of the
material for the paper.
