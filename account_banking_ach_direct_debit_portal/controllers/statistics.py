# Copyright 2025 Kencove (https://www.kencove.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from datetime import date

from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class StatisticsController(CustomerPortal):
    def _get_invoice_stats(self, date_from, date_to):
        """Get invoice statistics for a given date range."""
        AccountMove = request.env["account.move"].sudo()

        # Base domain for customer invoices
        base_domain = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
        ]

        # Total number of invoices
        total_invoices = AccountMove.search_count(base_domain)

        # Get all invoices in the date range
        invoices = AccountMove.search(base_domain)

        cc_paid_count = 0
        ach_paid_count = 0

        for invoice in invoices:
            payments = invoice._get_reconciled_payments()
            for payment in payments:
                if not payment.payment_method_line_id:
                    continue

                code = payment.payment_method_line_id.code

                if code == "ACH-In":
                    ach_paid_count += 1
                    break

                if code == "authorize":
                    cc_paid_count += 1
                    break

        return {
            "total": total_invoices,
            "paid_by_cc": cc_paid_count,
            "paid_by_ach": ach_paid_count,
        }

    def _get_portal_user_stats(self):
        """Get portal user statistics."""
        ResUsers = request.env["res.users"].sudo()
        ResPartner = request.env["res.partner"].sudo()
        AccountMove = request.env["account.move"].sudo()

        # Get all portal users
        portal_users = ResUsers.search(
            [("groups_id", "in", request.env.ref("base.group_portal").id)]
        )
        total_portal_users = len(portal_users)

        # Get partner IDs for portal users
        portal_partner_ids = portal_users.mapped("partner_id").ids

        # Portal users who have used portal for at least one invoice payment
        # (invoices paid by ACH or CC through portal)
        used_portal_payment_count = 0
        partners_with_portal_payment = set()

        invoices = AccountMove.search(
            [
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("partner_id", "in", portal_partner_ids),
                ("payment_state", "in", ("paid", "in_payment")),
            ]
        )

        for invoice in invoices:
            if invoice.partner_id.id in partners_with_portal_payment:
                continue
            payments = invoice._get_reconciled_payments()
            for payment in payments:
                if not payment.payment_method_line_id:
                    continue
                code = payment.payment_method_line_id.code
                if code in ("ACH-In", "authorize"):
                    partners_with_portal_payment.add(invoice.partner_id.id)
                    break

        used_portal_payment_count = len(partners_with_portal_payment)

        # Portal users with a bank account linked
        partners_with_bank = ResPartner.search_count(
            [
                ("id", "in", portal_partner_ids),
                ("bank_ids", "!=", False),
            ]
        )

        # Portal users with Autopay enabled
        partners_with_autopay = ResPartner.search_count(
            [
                ("id", "in", portal_partner_ids),
                ("autopay", "!=", "disabled"),
            ]
        )

        return {
            "total": total_portal_users,
            "used_portal_payment": used_portal_payment_count,
            "with_bank_account": partners_with_bank,
            "with_autopay": partners_with_autopay,
        }

    @http.route(["/stats"], type="http", auth="user", website=True)
    def statistics_page(self, **kw):
        # Check if user is in Administration/Settings group
        if not request.env.user.has_group("base.group_system"):
            return request.render(
                "account_banking_ach_direct_debit_portal.statistics_access_denied"
            )

        values = self._prepare_portal_layout_values()

        # Calculate date ranges
        today = date.today()
        this_year_start = date(today.year, 1, 1)
        this_year_end = date(today.year, 12, 31)
        last_year_start = date(today.year - 1, 1, 1)
        last_year_end = date(today.year - 1, 12, 31)

        # Get statistics for each year
        this_year_stats = self._get_invoice_stats(this_year_start, this_year_end)
        last_year_stats = self._get_invoice_stats(last_year_start, last_year_end)

        # Get portal user statistics
        portal_user_stats = self._get_portal_user_stats()

        values.update(
            {
                "page_name": "statistics",
                "this_year": today.year,
                "last_year": today.year - 1,
                "this_year_stats": this_year_stats,
                "last_year_stats": last_year_stats,
                "portal_user_stats": portal_user_stats,
            }
        )

        return request.render(
            "account_banking_ach_direct_debit_portal.statistics_page", values
        )
