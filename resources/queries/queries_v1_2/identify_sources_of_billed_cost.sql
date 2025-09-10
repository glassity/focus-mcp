-- Identify sources of billed cost
-- Source: https://focus.finops.org/use-case/identify-sources-of-billed-cost/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT ProviderName, PublisherName, InvoiceIssuer, InvoiceID, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ? GROUP BY ProviderName, PublisherName, InvoiceIssuer, InvoiceID