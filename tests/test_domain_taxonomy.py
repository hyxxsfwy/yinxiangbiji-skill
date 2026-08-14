import unittest


EXPECTED_DOMAINS = (
    "AI",
    "Quant",
    "信息技术",
    "投资理财",
    "知识管理",
    "健康医学",
    "中医",
    "两性情感",
    "个人成长",
    "科技产业",
    "自然科学",
    "文史社政",
)


class DomainRegistryTests(unittest.TestCase):
    def test_registry_exposes_the_twelve_managed_domains_in_display_order(self):
        from scripts.domain_taxonomy import MANAGED_DOMAINS

        self.assertEqual(MANAGED_DOMAINS, EXPECTED_DOMAINS)

    def test_legacy_domains_are_only_accepted_for_migration(self):
        from scripts.domain_taxonomy import canonical_domain

        with self.assertRaisesRegex(ValueError, "不支持的领域"):
            canonical_domain("软件工程")
        self.assertEqual(
            canonical_domain("软件工程", allow_legacy=True),
            "信息技术",
        )
        with self.assertRaisesRegex(ValueError, "不支持的领域"):
            canonical_domain("历史与社会")
        self.assertEqual(
            canonical_domain("历史与社会", allow_legacy=True),
            "文史社政",
        )

    def test_every_managed_domain_has_a_complete_classification_profile(self):
        from scripts.domain_taxonomy import (
            DOMAIN_PROFILES,
            MANAGED_DOMAINS,
            validate_domain_registry,
        )

        validate_domain_registry()
        self.assertEqual(tuple(DOMAIN_PROFILES), MANAGED_DOMAINS)
        for domain, profile in DOMAIN_PROFILES.items():
            with self.subTest(domain=domain):
                self.assertTrue(profile["core"])
                self.assertTrue(profile["support"])

    def test_all_domain_consumers_share_the_registry_order(self):
        from scripts.domain_taxonomy import MANAGED_DOMAINS
        from scripts.export_search_results import DOMAIN_PROFILES as export_profiles
        from scripts.reclassify_selected_materials import (
            DOMAIN_PROFILES as review_profiles,
            MANAGED_DOMAINS as review_domains,
        )
        from scripts.restructure_obsidian_vault import DOMAINS

        self.assertEqual(tuple(export_profiles), MANAGED_DOMAINS)
        self.assertEqual(tuple(review_profiles), MANAGED_DOMAINS)
        self.assertEqual(review_domains, MANAGED_DOMAINS)
        self.assertEqual(DOMAINS, MANAGED_DOMAINS)


if __name__ == "__main__":
    unittest.main()
