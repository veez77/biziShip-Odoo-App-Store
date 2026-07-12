# BiziShip for Odoo

**AI-powered LTL freight quoting and booking, built directly into Odoo Sales Orders.**

BiziShip connects your Odoo instance to the [BiziShip.ai](https://biziship.ai) LTL freight
platform. From a Sales Order, fetch live carrier quotes, compare rates, book shipments, and
auto-extract freight details from BOL PDFs — without leaving Odoo.

## Requirements

This module is a **connector** to the BiziShip.ai platform. It requires:

- A [BiziShip.ai](https://biziship.ai) account.
- A BiziShip API key, entered under **Settings → General Settings → BiziShip** after
  installing the module.

The module will not fetch quotes or book shipments without a configured API key.

## Key Features

- **Live LTL Quoting** — a dedicated "LTL Freight Details" tab on the Sales Order to enter
  cargo dimensions, auto-calculate freight class, and fetch real-time carrier quotes.
- **Quote Comparison & Booking** — compare carriers, transit days, and total charges, then
  book with one click.
- **AI BOL Extraction** — upload a Bill of Lading PDF and auto-populate freight details.
- **Recurring Pickup/Delivery Hours** — set weekly operating hours per shipment.
- **Shipment Notifications** — configurable email recipients (company defaults, salesperson,
  per-shipment extras) notified on booking, delivery, and cancellation.
- **Multi-Reference Numbers, Saved Freight Templates, Address History**, and more.

## Configuration

1. Install the module.
2. Go to **Settings → General Settings → BiziShip**.
3. Enter your BiziShip API key.
4. Open any Sales Order → **LTL Freight Details** tab to start quoting.

## Support

- Website: https://biziship.ai
- Support: support@biziship.ai

## License

LGPL-3
