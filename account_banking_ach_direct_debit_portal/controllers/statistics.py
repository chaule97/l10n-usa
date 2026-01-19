# Copyright 2025 Kencove (https://www.kencove.com)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from datetime import date

from psycopg2 import sql

from odoo import http
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal


class StatisticsController(CustomerPortal):
    def _get_invoice_stats(self, date_from, date_to):
        """Get invoice statistics for a given date range using SQL for performance."""
        cr = request.env.cr

        # Total number of invoices
        cr.execute(sql.SQL(
            """
                        SELECT COUNT(*)
                        FROM account_move
                        WHERE move_type = 'out_invoice'
                          AND state = 'posted'
                          AND invoice_date >= %s
                          AND invoice_date <= %s
                        """),
            (date_from, date_to)
        )
        total_invoices = cr.fetchone()[0]

        # Count invoices paid by ACH or CC using SQL
        # Join through reconciliation to find payment method codes
        cr.execute(sql.SQL(
            """
                        SELECT
                            pm.code,
                            COUNT(DISTINCT am.id) as invoice_count
                        FROM account_move am
                        JOIN account_move_line aml ON aml.move_id = am.id
                        JOIN account_partial_reconcile apr ON (
                            apr.credit_move_id = aml.id OR apr.debit_move_id = aml.id
                        )
                        JOIN account_move_line payment_aml ON (
                            (apr.debit_move_id = payment_aml.id AND apr.credit_move_id = aml.id)
                            OR (apr.credit_move_id = payment_aml.id AND apr.debit_move_id = aml.id)
                        )
                        JOIN account_move payment_move ON payment_move.id = payment_aml.move_id
                        JOIN account_payment ap ON ap.move_id = payment_move.id
                        JOIN account_payment_method_line pml ON pml.id = ap.payment_method_line_id
                        JOIN account_payment_method pm ON pm.id = pml.payment_method_id
                        WHERE am.move_type = 'out_invoice'
                          AND am.state = 'posted'
                          AND am.invoice_date >= %s
                          AND am.invoice_date <= %s
                          AND pm.code IN ('ACH-In', 'authorize')
                        GROUP BY pm.code
                        """
        ),
            (date_from, date_to),
        )

        results = cr.fetchall()
        cc_paid_count = 0
        ach_paid_count = 0

        for code, count in results:
            if code == "ACH-In":
                ach_paid_count = count
            elif code == "authorize":
                cc_paid_count = count

        return {
            "total": total_invoices,
            "paid_by_cc": cc_paid_count,
            "paid_by_ach": ach_paid_count,
        }

    def _get_portal_user_stats(self):
        """Get portal user statistics using SQL for performance."""
        cr = request.env.cr
        portal_group_id = request.env.ref("base.group_portal").id

        # Get total portal users count
        cr.execute(sql.SQL(
            """
                        SELECT COUNT(DISTINCT ru.id)
                        FROM res_users ru
                        JOIN res_groups_users_rel gur ON gur.uid = ru.id
                        WHERE gur.gid = %s
                        """
        ),
            (portal_group_id,),
        )
        total_portal_users = cr.fetchone()[0]

        # Get portal partner IDs for subsequent queries
        cr.execute(sql.SQL(
            """
                        SELECT DISTINCT rp.id
                        FROM res_partner rp
                        JOIN res_users ru ON ru.partner_id = rp.id
                        JOIN res_groups_users_rel gur ON gur.uid = ru.id
                        WHERE gur.gid = %s
                        """
        ),
            (portal_group_id,),
        )
        portal_partner_ids = [row[0] for row in cr.fetchall()]

        if not portal_partner_ids:
            return {
                "total": total_portal_users,
                "used_portal_payment": 0,
                "with_bank_account": 0,
                "with_autopay": 0,
            }

        # Count distinct partners who have used portal payment (ACH or CC)
        cr.execute(sql.SQL(
            """
                        SELECT COUNT(DISTINCT am.partner_id)
                        FROM account_move am
                        JOIN account_move_line aml ON aml.move_id = am.id
                        JOIN account_partial_reconcile apr ON (
                            apr.credit_move_id = aml.id OR apr.debit_move_id = aml.id
                        )
                        JOIN account_move_line payment_aml ON (
                            (apr.debit_move_id = payment_aml.id AND apr.credit_move_id = aml.id)
                            OR (apr.credit_move_id = payment_aml.id AND apr.debit_move_id = aml.id)
                        )
                        JOIN account_move payment_move ON payment_move.id = payment_aml.move_id
                        JOIN account_payment ap ON ap.move_id = payment_move.id
                        JOIN account_payment_method_line pml ON pml.id = ap.payment_method_line_id
                        JOIN account_payment_method pm ON pm.id = pml.payment_method_id
                        WHERE am.move_type = 'out_invoice'
                          AND am.state = 'posted'
                          AND am.partner_id = ANY(%s)
                          AND am.payment_state IN ('paid', 'in_payment')
                          AND pm.code IN ('ACH-In', 'authorize')
                        """
        ),
            (portal_partner_ids,),
        )
        used_portal_payment_count = cr.fetchone()[0]

        # Count partners with bank accounts linked
        cr.execute(sql.SQL(
            """
                        SELECT COUNT(DISTINCT rp.id)
                        FROM res_partner rp
                        JOIN res_partner_bank rpb ON rpb.partner_id = rp.id
                        WHERE rp.id = ANY(%s)
                        """
        ),
            (portal_partner_ids,),
        )
        partners_with_bank = cr.fetchone()[0]

        # Count partners with Autopay enabled
        cr.execute(sql.SQL(
            """
                        SELECT COUNT(*)
                        FROM res_partner
                        WHERE id = ANY(%s)
                          AND autopay IS NOT NULL
                          AND autopay != 'disabled'
                        """
        ),
            (portal_partner_ids,),
        )
        partners_with_autopay = cr.fetchone()[0]

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
