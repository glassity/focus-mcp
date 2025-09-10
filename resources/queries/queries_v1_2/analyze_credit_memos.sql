-- Analyze credit memos
-- Source: https://focus.finops.org/use-case/analyze-credit-memos/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, InvoiceID, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? AND ChargeCategory = 'Credit' GROUP BY ProviderName, InvoiceID