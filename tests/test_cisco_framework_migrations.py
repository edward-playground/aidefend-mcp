"""Current Cisco edition resolution, atomic consumer lookup, and ingestion contracts."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from app.framework_migrations import FrameworkMigrationRegistryError, canonical_lookup_id, resolve_framework_reference, validate_framework_migration_registry
from tests.framework_migration_fixtures import owasp_llm_2026_registry


def registry():
    value=owasp_llm_2026_registry()
    value['frameworks']['cisco']=json.loads((Path(__file__).parent/'fixtures/cisco-v2-catalog.json').read_text(encoding='utf-8'))
    value['registryVersion']='2026-09-11'
    return value


def resolve(query, value=None):
    return resolve_framework_reference(query, value or registry(), framework_key='cisco')


def test_current_catalog_and_all_ids_names():
    value=registry()
    assert validate_framework_migration_registry(value)==value
    items=value['frameworks']['cisco']['activeItems']
    for item in items:
        for query in [item['id'], 'Cisco v2 '+item['id'], item['id']+':2.0.0',item['id']+' '+item['name'],'Cisco '+item['name']]:
            result=resolve(query,value)
            if query=='Cisco '+item['name'] and sum(x['name']==item['name'] for x in items)>1:
                assert result['status']=='ambiguous'
                continue
            assert result['canonical']['id']==item['id'],query
            assert result['canonical']['edition']=='2.0.0'
            assert canonical_lookup_id(result)==item['id'].upper()


@pytest.mark.parametrize('query,code',[
 ('Cisco v1 AITech-2.1','unsupported_edition'),('AITech-2.1:v1.0.0','unsupported_edition'),
 ('Cisco version 1 AITech-2.1','unsupported_edition'),('AITech-1.4','retired_identifier'),
 ('AISubtech-1.2.1','retired_identifier'),('AITech-2.1 Jailbreak','id_name_conflict'),
 ('AITech-1.3 Goal Manipulation','id_name_conflict'),('AISubtech-15.1.25 Privacy Attacks: PII / PHI / PCI','id_name_conflict'),
 ('AITech-2.1 Goal Drift','id_name_conflict'),('Cisco Goal Manipulation','legacy_name_unsupported'),
 ('AITech-2.1:2.0.0x','malformed_or_unsupported_edition'),('Cisco v2.0.0x AITech-2.1','malformed_or_unsupported_edition'),
 ('AITech-2.1:','malformed_identifier'),('AITech-2.1.9','malformed_identifier'),('AISubtech-2.1','malformed_identifier'),
 ('AITech-02.1','malformed_identifier'),('AITech-2.1foo','malformed_identifier'),('AITech2.1','malformed_identifier'),
 ('AITech-999.1','unknown_identifier'),('Cisco v3 AITech-2.1','malformed_or_unsupported_edition'),('AITech-2.1 LLM03:2026','mixed_frameworks'),
])
def test_invalid_queries_have_no_canonical_lookup(query,code):
    result=resolve(query)
    assert result['status']=='invalid'
    assert result['reasonCode']==code
    assert canonical_lookup_id(result) is None


def test_retired_ids_and_multiple_candidates():
    for item in registry()['frameworks']['cisco']['historicalItems']:
        if item['status']=='retired':assert resolve(item['id'])['reasonCode']=='retired_identifier'
    for query in ['AITech-2.1 AITech-2.2','AITech-2.1/AISubtech-2.1.1','Cisco AITech-1.4; AITech-2.1']:
        assert resolve(query)['status']=='ambiguous'
    assert resolve('AML.T0051') is None


@pytest.mark.parametrize('mutation', ['duplicate','retired_current','current_missing','auto_migration','edition','digest','parent','policy'])
def test_registry_drift_rejected(mutation):
    value=registry();catalog=value['frameworks']['cisco']
    if mutation=='duplicate':catalog['activeItems'][1]['id']=catalog['activeItems'][0]['id']
    if mutation=='retired_current':catalog['historicalItems'][0]['id']='AITech-2.1'
    if mutation=='current_missing':catalog['activeItems'].pop()
    if mutation=='auto_migration':catalog['migrations']=[{}]
    if mutation=='edition':catalog['activeEdition']='1'
    if mutation=='digest':catalog['sourceArtifact']['sha256']='invalid'
    if mutation=='parent':next(x for x in catalog['activeItems'] if 'parentTechnique' in x)['parentTechnique']='AITech-999.1'
    if mutation=='policy':catalog['resolutionPolicy']['mappingCarryForward']='automatic'
    with pytest.raises(FrameworkMigrationRegistryError):validate_framework_migration_registry(value)


def test_query_routing_never_falls_back_to_legacy_regex():
    from app.tools.defenses_for_threat import _resolve_requested_threat_id
    for metadata in [None,{}, {'framework_migrations':owasp_llm_2026_registry()}]:
        resolution, identifier=_resolve_requested_threat_id('AITech-2.1',metadata)
        assert identifier is None
        assert resolution['reasonCode']=='registry_unavailable'
    for query in ['AITech-2.1 Jailbreak','Cisco v1 AITech-2.1','AITech-1.4','AITech-2.1/AITech-2.2']:
        result,identifier=_resolve_requested_threat_id(query,{'framework_migrations':registry()})
        assert identifier is None
        assert result['status'] in {'invalid','ambiguous'}
    result,identifier=_resolve_requested_threat_id('AITech-2.1',{'framework_migrations':registry()})
    assert identifier=='AITECH-2.1'
    assert result['canonical']['name']=='Excessive Agency'


def corpus(cisco_item):
    return [{'name':'Harden','techniques':[{'id':'AID-H-001','defendsAgainst':[
        {'framework':'OWASP LLM Top 10 2026','items':['LLM01:2026 Prompt Injection']},
        {'framework':'Cisco Integrated AI Security and Safety Framework','items':[cisco_item]},
    ]}]}]


def test_actual_ingestion_rejects_reused_v1_and_retired_item_semantics():
    from app.sync import validate_framework_migrations_corpus_contract
    validate_framework_migrations_corpus_contract(registry(),corpus('AITech-2.1 Excessive Agency'))
    for item in ['AITech-2.1 Jailbreak','AITech-1.4 Multi-Modal Injection and Manipulation','AISubtech-15.1.25 Privacy Attacks: PII / PHI / PCI']:
        with pytest.raises(FrameworkMigrationRegistryError):
            validate_framework_migrations_corpus_contract(registry(),corpus(item))


@pytest.mark.asyncio
async def test_actual_tool_returns_current_control_and_conflicts_no_generic_matches(monkeypatch):
    import app.core as core_module
    import app.tools.defenses_for_threat as defenses_module
    import app.utils as utils_module
    from tests.test_framework_migration_tool_resolution import FakeQueryEngine,_record
    engine=FakeQueryEngine([_record('AITech-2.1 Excessive Agency',framework='Cisco Integrated AI Security and Safety Framework')])
    monkeypatch.setattr(core_module,'query_engine',engine)
    monkeypatch.setattr(utils_module,'load_version_info',lambda:{'framework_migrations':registry(),'statistics':{'threat_mappings':{'AITECH-2.1':['AID-H-001.001']}}})
    rejected=await defenses_module.get_defenses_for_threat(threat_id='AITech-2.1 Jailbreak')
    assert rejected['search_method']=='resolution_only'
    # Metadata and rows are read under one generation snapshot; rejected input performs no matching.
    assert rejected['defense_techniques']==[]
    assert rejected['threat_query']['lookup_threat_id'] is None
    result=await defenses_module.get_defenses_for_threat(threat_id='Cisco v2 AITech-2.1')
    assert result['threat_query']['lookup_threat_id']=='AITECH-2.1'
    assert result['threat_query']['resolution']['canonical']['edition']=='2.0.0'
    assert result['total_results']==1
