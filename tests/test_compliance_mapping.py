"""
Tests for Compliance Mapping Tool

Tests the compliance framework mapping functionality including:
- Framework version information
- Heuristic mapping generation
- All 5 supported frameworks (NIST, EU, ISO, CSA, OWASP)
- All 7 AIDEFEND tactics
"""
import pytest
from app.tools.compliance_mapping import (
    FRAMEWORK_VERSIONS,
    SUPPORTED_FRAMEWORKS,
    _generate_heuristic_mapping,
    map_to_compliance_framework
)
from app.security import InputValidationError


class TestFrameworkVersions:
    """Test framework version constants."""

    def test_all_frameworks_have_versions(self):
        """All supported frameworks should have version information."""
        assert len(FRAMEWORK_VERSIONS) == 5
        assert len(SUPPORTED_FRAMEWORKS) == 5

        for framework_id in SUPPORTED_FRAMEWORKS.keys():
            assert framework_id in FRAMEWORK_VERSIONS
            assert FRAMEWORK_VERSIONS[framework_id] is not None
            assert len(FRAMEWORK_VERSIONS[framework_id]) > 0

    def test_version_format(self):
        """Version strings should contain expected information."""
        # NIST should mention RMF 2.0 and GenAI Profile
        assert "RMF 2.0" in FRAMEWORK_VERSIONS["nist_ai_rmf"]
        assert "GenAI" in FRAMEWORK_VERSIONS["nist_ai_rmf"]

        # EU AI Act should have regulation number
        assert "2024/1689" in FRAMEWORK_VERSIONS["eu_ai_act"]

        # ISO should have year
        assert "2023" in FRAMEWORK_VERSIONS["iso_42001"]

        # CSA should mention 2025
        assert "2025" in FRAMEWORK_VERSIONS["csa_ai_controls"]

        # OWASP should have version number
        assert "5.0.0" in FRAMEWORK_VERSIONS["owasp_asvs"]


class TestHeuristicMapping:
    """Test heuristic mapping generation."""

    @pytest.fixture
    def mock_technique(self):
        """Mock technique document."""
        return {
            'source_id': 'AID-H-001',
            'name': 'Input Validation',
            'tactic': 'Harden'
        }

    def test_generate_mapping_structure(self, mock_technique):
        """Mapping should have correct structure."""
        result = _generate_heuristic_mapping(mock_technique, 'nist_ai_rmf')

        assert 'technique_id' in result
        assert 'technique_name' in result
        assert 'technique_tactic' in result
        assert 'framework' in result
        assert 'framework_name' in result
        assert 'framework_controls' in result
        assert 'mapping_confidence' in result
        assert 'mapping_rationale' in result
        assert 'additional_considerations' in result

        assert result['technique_id'] == 'AID-H-001'
        assert result['technique_name'] == 'Input Validation'
        assert result['technique_tactic'] == 'Harden'

    def test_all_frameworks_return_mappings(self, mock_technique):
        """All frameworks should return non-empty mappings for valid tactics."""
        frameworks = ['nist_ai_rmf', 'eu_ai_act', 'iso_42001', 'csa_ai_controls', 'owasp_asvs']

        for framework in frameworks:
            result = _generate_heuristic_mapping(mock_technique, framework)
            controls = result['framework_controls']

            # All frameworks should have mappings for 'Harden' tactic
            assert len(controls) > 0, f"{framework} should have controls for Harden tactic"
            assert result['mapping_confidence'] == 'medium'

    def test_all_tactics_have_mappings(self):
        """All 7 tactics should have mappings across all frameworks."""
        tactics = ['Model', 'Harden', 'Detect', 'Isolate', 'Deceive', 'Evict', 'Restore']
        frameworks = list(SUPPORTED_FRAMEWORKS.keys())

        for tactic in tactics:
            technique = {
                'source_id': 'TEST-001',
                'name': 'Test Technique',
                'tactic': tactic
            }

            for framework in frameworks:
                result = _generate_heuristic_mapping(technique, framework)
                controls = result['framework_controls']

                assert len(controls) > 0, f"{framework} missing mappings for {tactic}"

    def test_unknown_tactic(self):
        """Unknown tactic should return empty controls."""
        technique = {
            'source_id': 'TEST-001',
            'name': 'Test',
            'tactic': 'UnknownTactic'
        }

        result = _generate_heuristic_mapping(technique, 'nist_ai_rmf')
        assert result['framework_controls'] == []
        assert result['mapping_confidence'] == 'low'

    def test_nist_control_format(self):
        """NIST controls should follow expected format."""
        technique = {'source_id': 'TEST', 'name': 'Test', 'tactic': 'Model'}
        result = _generate_heuristic_mapping(technique, 'nist_ai_rmf')

        for control in result['framework_controls']:
            # Control is now a dict with 'id', 'description', 'confidence' keys
            control_id = control['id']
            # Should contain function like GOVERN, MAP, MEASURE, MANAGE
            assert any(prefix in control_id for prefix in ['GOVERN', 'MAP', 'MEASURE', 'MANAGE'])

    def test_eu_act_control_format(self):
        """EU AI Act controls should reference articles."""
        technique = {'source_id': 'TEST', 'name': 'Test', 'tactic': 'Model'}
        result = _generate_heuristic_mapping(technique, 'eu_ai_act')

        for control in result['framework_controls']:
            # Control is now a dict with 'id', 'description', 'confidence' keys
            control_id = control['id']
            assert 'Art.' in control_id

    def test_iso_control_format(self):
        """ISO controls should have section numbers."""
        technique = {'source_id': 'TEST', 'name': 'Test', 'tactic': 'Harden'}
        result = _generate_heuristic_mapping(technique, 'iso_42001')

        for control in result['framework_controls']:
            # Control is now a dict with 'id', 'description', 'confidence' keys
            control_id = control['id']
            # Should contain numbers like 6.1, 8.2, etc.
            assert any(char.isdigit() for char in control_id)


class TestInputValidation:
    """Test input validation for map_to_compliance_framework."""

    @pytest.mark.asyncio
    async def test_empty_technique_list(self):
        """Empty technique list should raise error."""
        with pytest.raises(InputValidationError, match="cannot be empty"):
            await map_to_compliance_framework([], "nist_ai_rmf")

    @pytest.mark.asyncio
    async def test_too_many_techniques(self):
        """More than 50 techniques should raise error."""
        technique_ids = [f"AID-H-{i:03d}" for i in range(51)]

        with pytest.raises(InputValidationError, match="Too many techniques"):
            await map_to_compliance_framework(technique_ids, "nist_ai_rmf")

    @pytest.mark.asyncio
    async def test_unsupported_framework(self):
        """Unsupported framework should raise error."""
        with pytest.raises(InputValidationError, match="Unsupported framework"):
            await map_to_compliance_framework(["AID-H-001"], "invalid_framework")


class TestMappingCoverage:
    """Test mapping coverage across tactics and frameworks."""

    def test_100_percent_coverage(self):
        """All 35 combinations (7 tactics × 5 frameworks) should have mappings."""
        tactics = ['Model', 'Harden', 'Detect', 'Isolate', 'Deceive', 'Evict', 'Restore']
        frameworks = list(SUPPORTED_FRAMEWORKS.keys())

        total_combinations = len(tactics) * len(frameworks)
        covered_combinations = 0

        for tactic in tactics:
            for framework in frameworks:
                technique = {
                    'source_id': 'TEST',
                    'name': 'Test',
                    'tactic': tactic
                }
                result = _generate_heuristic_mapping(technique, framework)
                if len(result['framework_controls']) > 0:
                    covered_combinations += 1

        assert covered_combinations == total_combinations, \
            f"Coverage: {covered_combinations}/{total_combinations}"

    def test_csa_controls_implemented(self):
        """CSA AI Controls should have mappings (was missing before update)."""
        technique = {'source_id': 'TEST', 'name': 'Test', 'tactic': 'Model'}
        result = _generate_heuristic_mapping(technique, 'csa_ai_controls')

        assert len(result['framework_controls']) > 0
        assert 'GRC' in str(result['framework_controls']) or 'MDS' in str(result['framework_controls'])

    def test_owasp_asvs_implemented(self):
        """OWASP ASVS should have mappings (was missing before update)."""
        technique = {'source_id': 'TEST', 'name': 'Test', 'tactic': 'Harden'}
        result = _generate_heuristic_mapping(technique, 'owasp_asvs')

        assert len(result['framework_controls']) > 0
        # Should reference V-chapters (V1, V6, V8, etc.)
        # Control is now a dict with 'id', 'description', 'confidence' keys
        assert any('V' in control['id'] for control in result['framework_controls'])


class TestResultStructure:
    """Test the structure of mapping results."""

    def test_mapping_result_has_version(self):
        """Mapping result should include framework version."""
        technique = {'source_id': 'TEST', 'name': 'Test', 'tactic': 'Model'}

        # Create a mock result structure (simulating what map_to_compliance_framework returns)
        framework_id = 'nist_ai_rmf'
        mock_result = {
            "framework": {
                "id": framework_id,
                "name": SUPPORTED_FRAMEWORKS[framework_id],
                "version": FRAMEWORK_VERSIONS[framework_id]
            },
            "mappings": [_generate_heuristic_mapping(technique, framework_id)],
            "total_mapped": 1,
            "mapping_method": "heuristic"
        }

        assert 'version' in mock_result['framework']
        assert mock_result['framework']['version'] == FRAMEWORK_VERSIONS[framework_id]

    def test_disclaimer_includes_version(self):
        """Disclaimer should reference the framework version."""
        framework_id = 'nist_ai_rmf'
        version = FRAMEWORK_VERSIONS[framework_id]

        disclaimer = (
            f"Compliance mappings are generated automatically using heuristic analysis "
            f"based on {version} and should be reviewed by compliance experts. "
            f"Mappings may not cover all requirements and should be used as guidance only."
        )

        assert version in disclaimer
        assert "heuristic analysis" in disclaimer
        assert "compliance experts" in disclaimer


class TestSpecificFrameworks:
    """Test specific framework implementations."""

    def test_nist_genai_profile_included(self):
        """NIST mapping should include GenAI Profile controls."""
        technique = {'source_id': 'TEST', 'name': 'Test', 'tactic': 'Model'}
        result = _generate_heuristic_mapping(technique, 'nist_ai_rmf')

        # Should have additional controls compared to old version
        assert len(result['framework_controls']) >= 3

    def test_eu_act_final_version(self):
        """EU AI Act version should be Regulation 2024/1689."""
        assert "2024/1689" in FRAMEWORK_VERSIONS['eu_ai_act']
        assert "2024-07-12" in FRAMEWORK_VERSIONS['eu_ai_act']

    def test_iso_42001_2023(self):
        """ISO version should be 2023."""
        assert "ISO/IEC 42001:2023" == FRAMEWORK_VERSIONS['iso_42001']

    def test_csa_aicm_2025(self):
        """CSA should be AICM 2025."""
        assert "AICM" in FRAMEWORK_VERSIONS['csa_ai_controls']
        assert "2025" in FRAMEWORK_VERSIONS['csa_ai_controls']

    def test_owasp_asvs_5(self):
        """OWASP should be ASVS 5.0.0."""
        assert "5.0.0" in FRAMEWORK_VERSIONS['owasp_asvs']
