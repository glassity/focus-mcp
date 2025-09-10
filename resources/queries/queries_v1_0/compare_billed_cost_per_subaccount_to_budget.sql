-- Compare billed cost per subaccount to budget
-- Source: https://focus.finops.org/use-case/compare-billed-budget/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.0
-- FOCUS Version: v1.0

SELECT ProviderName, SubAccountId, SubAccountName, SUM(BilledCost) AS TotalBilledCost FROM focus_data WHERE ChargeCategory = 'Usage' AND ChargePeriodStart >= ? and ChargePeriodEnd <= ? AND ProviderName = ? AND SubAccountId = ? GROUP BY ProviderName, SubAccountId, SubAccountName