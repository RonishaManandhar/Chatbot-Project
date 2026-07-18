No. 4 - Phase 2: Customer Pages

Apply after Phase 1.

Changed files:
- app/static/css/customer-pages.css (new)
- app/templates/layouts/dashboard.base.html
- app/templates/customer/change_email.html

The stylesheet is loaded only when the logged-in role is Customer.
Agent and Administrator pages are not restyled by this phase.

After copying:
1. Restart Flask.
2. Press Ctrl+F5.
3. Test all Customer pages at desktop, tablet and narrow browser widths.
