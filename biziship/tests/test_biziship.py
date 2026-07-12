from odoo.tests.common import TransactionCase


class TestBiziShipSmoke(TransactionCase):
    """
    Minimal smoke test to satisfy the Odoo.sh build test requirement.
    Odoo.sh marks builds as 'Test: Failed' when 0 tests are found.
    """

    def test_module_loads(self):
        """Verify the biziship module is installed and models are accessible."""
        # Check that the biziship quote model exists and is queryable
        Quote = self.env['biziship.quote']
        self.assertIsNotNone(Quote, "biziship.quote model should be accessible")

    def test_sale_order_fields(self):
        """Verify our custom fields exist on sale.order."""
        order_fields = self.env['sale.order']._fields
        self.assertIn('biziship_route_miles', order_fields,
                      "biziship_route_miles field should exist on sale.order")
        self.assertIn('biziship_route_map_html', order_fields,
                      "biziship_route_map_html field should exist on sale.order")

    def test_res_users_fields(self):
        """Verify BiziShip auth fields exist on res.users."""
        user_fields = self.env['res.users']._fields
        self.assertIn('biziship_email', user_fields,
                      "biziship_email field should exist on res.users")
        self.assertIn('biziship_token', user_fields,
                      "biziship_token field should exist on res.users")
