-- Analyze marketplace vendors costs
-- Source: https://focus.finops.org/use-case/marketplace-vendors-costs/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT ChargePeriodStart, ChargePeriodEnd, ProviderName, PublisherName, InvoiceIssuerName, ROUND(SUM(EffectiveCost),2) AS TotalEffectiveCost FROM focus_data WHERE ChargePeriodStart >= ? AND ChargePeriodEnd < ? AND InvoiceIssuerName != PublisherName GROUP BY ChargePeriodStart, ChargePeriodEnd, ProviderName, PublisherName, InvoiceIssuerName ORDER BY TotalEffectiveCost ASC