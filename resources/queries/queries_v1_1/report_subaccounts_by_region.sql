-- Report subaccounts by region
-- Source: https://focus.finops.org/use-case/report-subaccount-regions/?prod_use_cases%5Bmenu%5D%5Bversions%5D=v1.1
-- FOCUS Version: v1.1

SELECT ProviderName, SubAccountId, RegionId RegionName, COUNT(1) FROM focus_data WHERE ChargePeriodStart >= ? AND ChargePeriodEnd < ? GROUP BY ProviderName, SubAccountId, RegionId, RegionName