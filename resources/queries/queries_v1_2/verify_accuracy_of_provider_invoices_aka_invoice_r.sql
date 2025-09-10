-- Verify accuracy of provider invoices aka invoice reconciliation
-- Source: https://focus.finops.org/use-case/verify-accuracy-of-provider-invoices-aka-invoice-reconciliation/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT InvoiceIssuer, InvoiceID, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY InvoiceIssuer, InvoiceID