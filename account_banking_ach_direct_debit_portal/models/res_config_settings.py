from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    plaid_env = fields.Selection(
        [
            ("sandbox", "Sandbox"),
            ("development", "Development"),
            ("production", "Production"),
        ],
        string="Plaid Environment",
        default="sandbox",
        help="Plaid environment to use (Sandbox, Development or Production).",
        config_parameter="account_banking_ach_direct_debit_portal.plaid_env",
    )

    plaid_client_id = fields.Char(
        "Client ID",
        help="Client ID provided by Plaid",
        config_parameter="account_banking_ach_direct_debit_portal.plaid_client_id",
    )

    plaid_secret = fields.Char(
        "Secret",
        help="Secret Key provided by Plaid",
        config_parameter="account_banking_ach_direct_debit_portal.plaid_secret",
    )

    credit_card_surcharge = fields.Float(
        string="Credit Card Surcharge (%)",
        config_parameter="account_banking_ach_direct_debit_portal.credit_card_surcharge",
        default=3.0,
        help="Surcharge percentage to apply "
        "when customers pay with a credit card on the portal.",
    )
