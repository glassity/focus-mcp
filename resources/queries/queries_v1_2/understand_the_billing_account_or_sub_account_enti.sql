-- Understand the billing account or sub account entity
-- Source: https://focus.finops.org/use-case/understand-the-billing-account-or-sub-account-entity/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.2
-- FOCUS Version: v1.2

SELECT DISTINCT ProviderName, BillingAccountID, BillingAccountName, BillingAccountType FROM focus_data WHERE ChargePeriodStart >= ? and ChargePeriodEnd < ?