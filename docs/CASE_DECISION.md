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

Use the official Nutrient Data Extraction API endpoint selected for typed
invoice extraction:

```text
POST https://api.nutrient.io/extraction/extract
```

The request uploads the local document as multipart field `file` and sends an
outer `instructions` JSON object containing a schema, parse configuration, and
citations:

```json
{
  "schema": {"type": "object", "properties": {
    "vendor_name": {"type": "string"},
    "invoice_number": {"type": "string"},
    "issue_date": {"type": "string"},
    "currency": {"type": "string"},
    "total_amount": {"type": "number"},
    "line_items": {"type": "array"}
  }},
  "parseConfig": {"mode": "structure"},
  "options": {"includeCitations": true}
}
```

The official extract documentation distinguishes this from
`/extraction/parse`: `extract` maps a document to typed JSON and returns
`output.data` plus per-field `output.metadata` citations and confidence. This
is the better contract for an invoice because the pipeline needs named fields,
not only general spatial elements.

The official Python client also exposes the extraction capability through
`NutrientClient.parse`; the first implementation uses the documented HTTP
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
- [Extract endpoint](https://www.nutrient.io/guides/dws-data-extraction/extract/)
- [Citations and confidence](https://www.nutrient.io/guides/dws-data-extraction/extract/citations-and-confidence/)
- [Invoice extraction](https://www.nutrient.io/api/data-extraction-api/invoices/)
- [Official Python client](https://github.com/PSPDFKit/nutrient-dws-client-python)
