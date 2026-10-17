# Third-party notices

Bridge is released under the MIT License (see `LICENSE`), copyright Team Malai Ren. It uses the
third-party code, models, fonts, data and services listed below, each under its own licence. The
licences were read from each package's own metadata in the built backend image and from
`frontend/package-lock.json`. The full licence texts ship with the packages themselves (Python:
`site-packages/*.dist-info/`; JavaScript: `node_modules/*/LICENSE`; Debian packages:
`/usr/share/doc/*/copyright`).

## Backend: Python packages we depend on directly

| Package | Version | Licence | Used for |
|---|---|---|---|
| fastapi | 0.143.0 | MIT | Web API |
| uvicorn | 0.54.0 | BSD-3-Clause | Web server |
| pydantic | 2.14.0 | MIT | Data validation |
| sqlalchemy | 2.1.4 | MIT | Database access |
| python-multipart | 0.0.32 | Apache-2.0 | File uploads |
| sse-starlette | 3.5.0 | BSD-3-Clause | Server-Sent Events |
| httpx | 0.28.1 | BSD-3-Clause | HTTP client (FX rates, rule sources) |
| anthropic | 1.12.1 | MIT | Claude API client |
| sentence-transformers | 6.1.0 | Apache-2.0 | Multilingual embeddings |
| pdfplumber | 0.11.10 | MIT | Reading PDF text |
| pytesseract | 0.3.13 | Apache-2.0 | OCR for images |
| pillow | 12.3.0 | MIT-CMU | Images |
| reportlab | 5.0.1 | BSD-3-Clause | Generating the demo PDFs and receipts |
| pytest | 9.1.1 | MIT | Tests |

## Backend: other Python packages in the image (installed by the ones above)

| Package | Version | Licence |
|---|---|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| cloudpickle | 3.1.2 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| docstring_parser | 0.18.0 | MIT |
| filelock | 3.32.3 | MIT |
| fsspec | 2026.7.0 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| hf-xet | 1.7.0 | Apache-2.0 |
| httpcore, httpcore2, httpx2 | 1.0.9, 2.13.1, 2.13.1 | BSD-3-Clause |
| huggingface_hub | 1.33.0 | Apache-2.0 |
| idna | 3.20 | BSD-3-Clause |
| iniconfig | 2.3.1 | MIT |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| jiter | 0.17.0 | MIT |
| joblib | 1.6.0 | BSD-3-Clause |
| markdown-it-py | 4.2.0 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| mdurl | 0.1.2 | MIT |
| mpmath | 1.3.0 | BSD-3-Clause |
| narwhals | 2.26.0 | MIT |
| networkx | 3.6.1 | BSD-3-Clause |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| opentelemetry-api | 1.45.1 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pdfminer.six | 20260107 | MIT |
| pip | 24.0 | MIT |
| pluggy | 1.6.0 | MIT |
| pycparser | 3.11 | BSD-3-Clause |
| pydantic_core | 2.50.0 | MIT |
| Pygments | 2.21.0 | BSD-2-Clause |
| pypdfium2 | 5.14.0 | BSD-3-Clause, Apache-2.0 (PDFium) |
| PyYAML | 6.0.3 | MIT |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python |
| rich | 15.0.0 | MIT |
| safetensors | 0.8.0 | Apache-2.0 |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| scipy | 1.17.1 | BSD-3-Clause |
| setuptools | 79.0.1 | MIT |
| shellingham | 1.5.4 | ISC |
| sniffio | 1.3.1 | MIT OR Apache-2.0 |
| starlette | 1.7.0 | BSD-3-Clause |
| sympy | 1.14.0 | BSD-3-Clause |
| threadpoolctl | 3.7.0 | BSD-3-Clause |
| tokenizers | 0.23.2 | Apache-2.0 |
| torch (CPU) | 2.14.1 | Apache-2.0 AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT (with LLVM exception) |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| transformers | 5.19.0 | Apache-2.0 |
| truststore | 0.10.4 | MIT |
| typer | 0.27.3 | MIT |
| typing-inspection | 0.4.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| wheel | 0.46.3 | MIT |

## Backend: system packages and model in the Docker image

| Component | Version | Licence | Used for |
|---|---|---|---|
| python:3.11-slim base image (Debian) | 3.11 | PSF-2.0 (Python); Debian packages under their own licences | Runtime |
| tesseract-ocr, libtesseract5 | 5.5.0 | Apache-2.0 | OCR engine |
| tesseract-ocr-chi-sim | 4.1.0 | Apache-2.0 | Simplified Chinese OCR data |
| fonts-wqy-zenhei (WenQuanYi Zen Hei) | 0.9.45 | GPL-2.0 with font embedding exception | Chinese text in the generated demo PDFs and receipts (the exception allows embedding the font in documents) |
| sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 | from Hugging Face | Apache-2.0 | Multilingual passage search |

## Frontend: JavaScript packages we depend on directly

| Package | Version | Licence | Used for |
|---|---|---|---|
| next | 16.4.0 | MIT | Web framework |
| react, react-dom | 19.3.0 | MIT | User interface |
| clsx | 2.1.1 | MIT | Class names |
| lucide-react | 1.53.0 | ISC | Icons |
| tailwindcss, @tailwindcss/postcss | 4.3.3 | MIT | Styles (build time) |
| typescript | 7.0.2 | Apache-2.0 | Type checking (build time) |
| @types/node, @types/react, @types/react-dom | 24.19.1, 19.3.0 | MIT | Type definitions |
| @playwright/test | 1.64.1 | Apache-2.0 | End-to-end test and demo video recorder |
| node:24-alpine base image | 24 | MIT (Node.js); Alpine packages under their own licences | Runtime |

## Frontend: other JavaScript packages (installed by the ones above)

`frontend/package-lock.json` lists every one. All packages in it, the direct ones included, by licence: MIT (52), Apache-2.0 (40), ISC (4), MPL-2.0 (12, build time only), LGPL-3.0-or-later (14, optional platform builds), CC-BY-4.0 (1), BSD-3-Clause (1), 0BSD (1). The ones not under MIT, Apache-2.0 or ISC:

| Package | Licence | Notes |
|---|---|---|
| @img/sharp-libvips-* and @img/sharp-* platform builds | LGPL-3.0-or-later (libvips), Apache-2.0 (sharp) | Optional prebuilt image library that Next.js may load for image optimisation; used unmodified as a separate shared library |
| lightningcss and its platform builds | MPL-2.0 | CSS processing, build time only; unmodified |
| caniuse-lite | CC-BY-4.0 | Browser-support data used at build time; data by the Can I Use project (caniuse.com) |
| source-map-js | BSD-3-Clause | Source maps |
| tslib | 0BSD | TypeScript helpers |

## Fonts

| Font | Licence | Used for |
|---|---|---|
| IBM Plex Sans | SIL Open Font License 1.1 | Body text (served by next/font from Google Fonts, self-hosted at build time); subtitles of the demo video |
| Space Grotesk | SIL Open Font License 1.1 | Headings and amounts |
| WenQuanYi Zen Hei | GPL-2.0 with font embedding exception | Chinese text in generated PDFs (see above) |

## Data and services

| Source | Terms | Used for |
|---|---|---|
| Frankfurter API (api.frankfurter.app) | Open source (MIT); serves European Central Bank reference rates | Mid-market FX rates, frozen at each demo reset |
| European Central Bank euro foreign exchange reference rates | Free reuse with the source acknowledged | The rates behind Frankfurter |
| Anthropic Claude API | Anthropic's commercial terms; not distributed with Bridge | Live mode: extraction, claims and agent replies (needs the user's own API key) |
| Public fee-scam warnings (University of Technology Sydney, University of Sussex) and the Australian Federal Police's money-mule warning | Referenced by link; not copied | Background for the demo story. In live mode a person can add such a page as a rule source; Bridge then stores only short supporting sentences with a link to the page. |

## Tools used to make the evidence (not part of Bridge, not distributed)

Google Chrome (for the end-to-end test and the video recorder), FFmpeg (video encoding) and Poppler (pdftoppm, pdftotext; rendering the invoice for the video) run on the developer's machine only. Their outputs (the video and screenshots) contain no part of these tools.

## Fictional content

All institutions, banks, people and accounts in the demo data and documents (Shenzhen Polytechnic International University, Shenzhen Bay Commercial Bank, Ahmad Faris and others) are fictional. The SPIU crest is an original drawing made for this project.
