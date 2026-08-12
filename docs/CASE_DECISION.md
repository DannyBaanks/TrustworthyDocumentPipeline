# Case Decision

## Selected Case

Process one non-sensitive invoice PDF and route it to automatic approval or
human review.

The demo invoice will contain synthetic values only:

- vendor name;
- invoice number;
- issue date;
- currency;
- line items;
- total due.

## Nutrient Operation

Use the official Nutrient Data Extraction API endpoint:

```text
POST https://api.nutrient.io/extraction/parse
```

The request uploads the local PDF as multipart field `file` and sends:

```json
{"mode":"structure","output":{"format":"spatial"}}
```

The API documentation states that spatial output contains document elements
with confidence, bounds, and page context, including tables and key-value
regions. This gives the pipeline real source-grounded extraction data without
inventing confidence values.

The official Python client also exposes the same extraction capability through
`NutrientClient.parse`. The first implementation will use the documented HTTP
contract so the request and response remain visible during integration tests.

## Why This Case

- It satisfies the sponsor requirement that DWS perform a meaningful document
  operation.
- The input can be a synthetic invoice with no personal information.
- Confidence and source coordinates are directly relevant to review.
- Validation is concrete but small: required fields, numeric totals, and line
  item consistency.
- The two-minute demo is easy to understand.
- The case can later extend to document-set reconciliation without forcing
  that complexity into the first version.

## Deliberately Deferred

- Multi-document matching.
- Digital signing.
- Redaction.
- OCR fallback.
- Agentic mode.
- Schema-generator integration.

Those features will enter only if the real response or the challenge demo
requires them.

## Official Sources

- [Data Extraction API](https://www.nutrient.io/api/data-extraction-api/)
- [Data Extraction getting started](https://www.nutrient.io/guides/dws-data-extraction/getting-started/)
- [Invoice extraction](https://www.nutrient.io/api/data-extraction-api/invoices/)
- [Official Python client](https://github.com/PSPDFKit/nutrient-dws-client-python)
