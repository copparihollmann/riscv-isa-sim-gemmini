#!/usr/bin/env python3
"""Freeze and verify the local Iris elaboration's memory routes, not calibration."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
DEFAULT_ROOT = Path('/scratch/eygao/iris-cy')
GENERATED = 'sims/firesim-staging/generated-src/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig/'
PREFIX = GENERATED + 'firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig.'
NS = {'g': 'http://graphml.graphdrawing.org/xmlns'}


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def extract_lines(path, ranges):
    selected = []
    with Path(path).open('rb') as stream:
        for number, line in enumerate(stream, 1):
            if any(first <= number <= last for first, last in ranges):
                selected.append(line)
            if number >= ranges[-1][1]:
                break
    if len(selected) != sum(last - first + 1 for first, last in ranges):
        raise ValueError('source line extraction is incomplete')
    return b''.join(selected)


def select_annotation(path, selector):
    matches = [item for item in json.loads(Path(path).read_text())
               if all(item.get(key) == value for key, value in selector.items())]
    if len(matches) != 1:
        raise ValueError('annotation selector is ambiguous or absent')
    return (json.dumps(matches[0], indent=2) + '\n').encode()


def validate(data, live_root=None):
    if data.get('schema_version') != 1 or data.get('scope') != 'local-elaboration-memory-path-audit':
        raise ValueError('unsupported memory audit schema')
    if data['calibrated'] or data['deployed_image_association_verified']:
        raise ValueError('this source audit cannot certify timing or the deployed image')
    if data.get('generator_sha256') != sha(Path(__file__)):
        raise ValueError('memory audit generator changed; regenerate after review')
    lengths = {}
    checked = {}
    for identity, source in data['sources'].items():
        if not re.fullmatch('[0-9a-f]{40}', source['repository_commit']):
            raise ValueError('full repository commit required')
        if source['repository_commit'] != data['repositories'][source['repository']]['commit']:
            raise ValueError('source repository mismatch: ' + identity)
        snapshot = HERE / source['snapshot']
        if sha(snapshot) != source['sha256']:
            raise ValueError('memory source digest mismatch: ' + identity)
        lengths[identity] = len(snapshot.read_bytes().splitlines())
        if live_root:
            actual = Path(live_root) / source['path']
            if actual not in checked:
                checked[actual] = sha(actual)
            if checked[actual] != source.get('original_sha256', source['sha256']):
                raise ValueError('live memory evidence changed: ' + identity)
            if 'line_ranges' in source and extract_lines(actual, source['line_ranges']) != snapshot.read_bytes():
                raise ValueError('memory excerpt is not the declared original lines')
            if 'json_selector' in source and select_annotation(actual, source['json_selector']) != snapshot.read_bytes():
                raise ValueError('memory annotation excerpt changed')
    for repository in data['repositories'].values():
        if 'patch' in repository and sha(HERE / repository['patch']) != repository['tracked_diff_sha256']:
            raise ValueError('memory repository patch digest mismatch')
    for group in ('facts', 'routes', 'local_aliases', 'calibration_probes'):
        for fact in data[group]:
            for ref in fact['evidence']:
                first, last = ref['lines']
                if not 1 <= first <= last <= lengths[ref['source']]:
                    raise ValueError('invalid memory citation: ' + fact['id'])
    routes = {(row['hart'], row['requester'], row['region']) for row in data['routes']}
    expected = {(h, requester, region) for h in range(3)
                for requester in ('instruction', 'scalar_data', 'vector_data')
                for region in ('tcm0', 'tcm1', 'scratchpad', 'dram')}
    if routes != expected or len(data['routes']) != 36:
        raise ValueError('missing or duplicate per-hart memory route')
    if any(row['fitted_latency_cycles'] is not None for row in data['routes']):
        raise ValueError('source routes cannot supply fitted latency')
    v1 = json.loads((WORKSPACE / 'benchmarks/calibration-corpus.json').read_text())
    v2 = json.loads((WORKSPACE / 'benchmarks/v2/corpus.json').read_text())
    available = {row['case_id'] for row in v1['cases'] + v2['cases']}
    for probe in data['calibration_probes']:
        if not set(probe['existing_case_ids']) <= available:
            raise ValueError('calibration mapping names an absent experiment')
    if any(value is not None for value in data['unmeasured_timing_parameters'].values()):
        raise ValueError('source audit cannot supply fitted timing values')
    for relative, expected_sha in data['benchmark_input_sha256'].items():
        if sha(WORKSPACE / relative) != expected_sha:
            raise ValueError('benchmark input changed; re-audit probe mapping: ' + relative)
    return {'source_count': len(lengths), 'route_count': len(routes),
            'source_integrity_passed': True, 'calibrated': False,
            'deployed_image_association_verified': False}


def generate(root):
    baseline = json.loads((HERE / 'manifest.json').read_text())
    previous_path = HERE / 'memory-paths.json'
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
    sources, repositories = {}, {}
    evidence = HERE / 'memory-evidence'
    evidence.mkdir(exist_ok=True)
    for key in ('chipyard', 'saturn', 'rocket-chip', 'shuttle', 'testchipip', 'firesim'):
        item = baseline['repositories'][key]
        repositories[key] = {'commit': item['commit'], 'tracked_modified': item['tracked_modified'],
                             'tracked_diff_sha256': item['tracked_diff_sha256'], 'patch': item['tracked_diff']}
    for key, path in [('inclusive-cache', 'generators/rocket-chip-inclusive-cache'),
                      ('constellation', 'generators/constellation')]:
        repo = root / path
        git = ['git', '-c', 'safe.directory=' + str(repo), '-C', str(repo)]
        commit = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
        patch = subprocess.check_output(git + ['diff', '--binary', 'HEAD'])
        destination = evidence / (key + '.patch')
        destination.write_bytes(patch)
        repositories[key] = {'commit': commit, 'tracked_modified': bool(patch),
                             'tracked_diff_sha256': sha(destination), 'patch': str(destination.relative_to(HERE))}

    def source(identity, path, repository, ranges=None, selector=None):
        original = root / path
        if previous and identity in previous['sources']:
            old = previous['sources'][identity]
            if sha(original) != old.get('original_sha256', old['sha256']):
                raise ValueError('reviewed memory input changed; re-audit the manually derived routes/parameters before regeneration: ' + identity)
        raw = extract_lines(original, ranges) if ranges else select_annotation(original, selector) if selector else original.read_bytes()
        suffix = '.txt' if ranges else '.json' if selector else Path(path).suffix
        destination = evidence / (identity + suffix)
        destination.write_bytes(raw)
        entry = {'path': path, 'repository': repository, 'repository_commit': repositories[repository]['commit'],
                 'snapshot': str(destination.relative_to(HERE)), 'sha256': sha(destination),
                 'source_state': 'local elaboration; build-input/deployed-image association unverified' if path.startswith(GENERATED) else 'identified local working-tree bytes'}
        if ranges or selector:
            entry['original_sha256'] = sha(original)
        if ranges:
            entry['line_ranges'] = ranges
            offset = 1
            entry['original_line_mapping'] = []
            for first, last in ranges:
                entry['original_line_mapping'].append({'snapshot_first_line': offset, 'original_first_line': first, 'line_count': last-first+1})
                offset += last-first+1
        if selector:
            entry['json_selector'] = selector
        sources[identity] = entry
        return destination.read_text()

    paths = [
        ('iris', 'generators/chipyard/src/main/scala/config/IrisConfigs.scala', 'chipyard'),
        ('target', 'generators/firechip/chip/src/main/scala/TargetConfigs.scala', 'chipyard'),
        ('bridge-binders', 'generators/firechip/chip/src/main/scala/BridgeBinders.scala', 'chipyard'),
        ('shuttle-tile', 'generators/shuttle/src/main/scala/common/Tile.scala', 'shuttle'),
        ('shuttle-offset', 'generators/shuttle/src/main/scala/common/AddressOffsetter.scala', 'shuttle'),
        ('shuttle-config', 'generators/shuttle/src/main/scala/common/Configs.scala', 'shuttle'),
        ('shuttle-icache', 'generators/shuttle/src/main/scala/ifu/ICache.scala', 'shuttle'),
        ('shuttle-pma', 'generators/shuttle/src/main/scala/dmem/PMA.scala', 'shuttle'),
        ('shuttle-tlb', 'generators/shuttle/src/main/scala/dmem/TLB.scala', 'shuttle'),
        ('shuttle-core-params', 'generators/shuttle/src/main/scala/common/Parameters.scala', 'shuttle'),
        ('saturn-params', 'generators/saturn/src/main/scala/common/Parameters.scala', 'saturn'),
        ('saturn-rocket', 'generators/saturn/src/main/scala/rocket/Integration.scala', 'saturn'),
        ('saturn-shuttle', 'generators/saturn/src/main/scala/shuttle/Integration.scala', 'saturn'),
        ('saturn-shuttle-config', 'generators/saturn/src/main/scala/shuttle/Configs.scala', 'saturn'),
        ('saturn-rocket-config', 'generators/saturn/src/main/scala/rocket/Configs.scala', 'saturn'),
        ('saturn-tl', 'generators/saturn/src/main/scala/mem/TLInterface.scala', 'saturn'),
        ('scratch', 'generators/testchipip/src/main/scala/soc/Scratchpad.scala', 'testchipip'),
        ('scratch-config', 'generators/testchipip/src/main/scala/soc/Configs.scala', 'testchipip'),
        ('replication', 'generators/rocket-chip/src/main/scala/tilelink/RegionReplication.scala', 'rocket-chip'),
        ('sram', 'generators/rocket-chip/src/main/scala/tilelink/SRAM.scala', 'rocket-chip'),
        ('buffer', 'generators/rocket-chip/src/main/scala/tilelink/Buffer.scala', 'rocket-chip'),
        ('async', 'generators/rocket-chip/src/main/scala/tilelink/AsyncCrossing.scala', 'rocket-chip'),
        ('rocket-tlb', 'generators/rocket-chip/src/main/scala/rocket/TLB.scala', 'rocket-chip'),
        ('l2-config', 'generators/rocket-chip-inclusive-cache/design/craft/inclusivecache/src/Configs.scala', 'inclusive-cache'),
        ('l2-params', 'generators/rocket-chip-inclusive-cache/design/craft/inclusivecache/src/Parameters.scala', 'inclusive-cache'),
        ('noc-tl', 'generators/constellation/src/main/scala/protocol/Tilelink.scala', 'constellation'),
        ('fased-config', 'sims/firesim/sim/midas/src/main/scala/configs/FASEDTargetConfigs.scala', 'firesim'),
        ('compiler-config', 'sims/firesim/sim/midas/src/main/scala/configs/CompilerConfigs.scala', 'firesim'),
        ('latency-pipe', 'sims/firesim/sim/midas/src/main/scala/midas/models/dram/LatencyBandwidthPipe.scala', 'firesim'),
        ('fased-driver', 'sims/firesim/sim/midas/src/main/cc/bridges/fased_memory_timing_model.cc', 'firesim'),
        ('graph0', PREFIX + 'chiptop0.graphml', 'chipyard'),
        ('graph1', PREFIX + 'chiptop1.graphml', 'chipyard'),
        ('l2', PREFIX + 'l2.json', 'chipyard'),
        ('dts', PREFIX + 'dts', 'chipyard'),
        ('clocks', PREFIX + 'firesimRationalClockBridge.freq-summary', 'chipyard'),
        ('elaboration-log', PREFIX + 'chisel.log', 'chipyard'),
        ('historical-success-argv', 'sims/firesim/deploy/results-workload/2026-11-04--23-20-38-bare/bare0/sim-run.sh', 'firesim'),
        ('historical-failed-argv', 'sims/firesim/deploy/results-workload/2026-11-05--04-26-53-bare/bare0/sim-run.sh', 'firesim'),
    ]
    texts = {identity: source(identity, path, repository) for identity, path, repository in paths}
    texts['clock-annotation'] = source('clock-annotation', PREFIX + 'anno.json', 'chipyard', selector={
        'class': 'firesim.lib.bridgeutils.BridgeAnnotation', 'target': '~FireSim|RationalClockBridge'})
    texts['fased-annotation'] = source('fased-annotation', PREFIX + 'anno.json', 'chipyard', selector={
        'class': 'firesim.lib.bridgeutils.BridgeAnnotation', 'target': '~FireSim|FASEDBridge'})
    texts['fir-clocks'] = source('fir-clocks', PREFIX + 'fir', 'chipyard', ranges=[
        [2414059, 2414144], [2414218, 2414262], [2414423, 2414442], [2414515, 2414515],
        [2414547, 2414551], [2415175, 2415178], [2534866, 2534868], [2534933, 2534935], [2534981, 2535013]])
    texts['fir-alias'] = source('fir-alias', PREFIX + 'fir', 'chipyard', ranges=[
        [422334, 422350], [422476, 422485], [422592, 422599],
        [1147476, 1147485], [1147558, 1147569], [1992529, 1992540]])

    def ref(identity, anchor, end=None):
        lines = texts[identity].splitlines()
        start = next((i for i, line in enumerate(lines, 1) if anchor in line), None)
        if start is None:
            raise ValueError('missing source anchor: ' + identity + ': ' + anchor)
        if end:
            stop = next((i for i, line in enumerate(lines, 1) if i >= start and end in line), None)
            if stop is None:
                raise ValueError('missing end anchor')
        else:
            stop = start
        return {'source': identity, 'lines': [start, stop]}

    def graph_ref(node):
        return ref('graph0', '<node id="' + node + '">', '</node>')

    facts = []
    def fact(identity, value, refs, interpretation=None):
        row = {'id': identity, 'value': value, 'evidence': refs}
        if interpretation:
            row['interpretation'] = interpretation
        facts.append(row)

    graph = ET.fromstring(texts['graph0'])
    node_descriptions = {}
    for node in graph.findall('.//g:node', NS):
        description = node.find('g:data[@key="d"]', NS)
        node_descriptions[node.attrib['id']] = ''.join(description.itertext()) if description is not None else ''
    for node, width in [('112::0', 32), ('115::0', 32), ('162::0', 32), ('165::0', 32),
                        ('311::0', 8), ('318::0', 8), ('54::0', 8), ('128::0', 8), ('178::0', 8), ('277::0', 8)]:
        observed = {int(value) for value in re.findall(r'Slave Port Beatbytes = (\d+)', node_descriptions[node])}
        if observed != {width}:
            raise ValueError('elaborated memory port width changed: ' + node)
    for node in ('94::0', '144::0'):
        if 'AddressSet(0x70080000, 0x7ffbf)' not in node_descriptions[node]:
            raise ValueError('private TCM alias mask changed')

    fact('hart-vector-widths-bits', {'0': {'vlen':256,'dlen':128,'mlen':128},
         '1': {'vlen':256,'dlen':128,'mlen':128},'2': {'vlen':256,'dlen':256,'mlen':256}},
         [ref('iris','WithRocketVectorUnit(256, 256'),ref('iris','new saturn.shuttle.WithShuttleVectorUnit(', 'VectorParams.opuMxParams'),
          ref('saturn-shuttle-config','mLen=mLen.getOrElse(dLen)'),
          ref('saturn-rocket-config','params.copy(dLen=dLen, mLen=mLen.getOrElse(dLen))'),ref('saturn-params','def mLen =')])
    fact('vector-memory-routing', {'0':'independent TLSplitInterface/atlNode; bypass scalar L1D',
         '1':'independent TLSplitInterface/atlNode; bypass scalar L1D',
         '2':'load_use_tl_reg/store_use_tl_reg both true without writers; TLSplitInterface/atlNode; bypass scalar L1D'},
         [ref('saturn-shuttle','val tl_if =','atlNode :='),ref('saturn-rocket','val load_use_tl_reg =','val store_use_tl ='),
          ref('saturn-rocket','when (load_use_tl)','when (store_use_tl)'),ref('saturn-tl','class TLSplitInterface','arb.node := writer.node')],
         'The useL1DCache option/comment does not change the constant-true routing registers in this source.')
    fact('vector-aligned-request-bytes', {'0':16,'1':16,'2':32},
         [ref('saturn-shuttle-config','mLen=mLen.getOrElse(dLen)'),
          ref('saturn-rocket-config','params.copy(dLen=dLen, mLen=mLen.getOrElse(dLen))'),
          ref('saturn-tl','val widthBytes =','val offBits ='),
          ref('saturn-tl','out.a.bits := Mux','out.d.ready := true.B'),
          ref('saturn-tl','def node = TLWidthWidget(mLenB)')],
         'TLInterface issues aligned full-width Get/Put transactions using masks for stores. Narrow uncore links fragment/serialize these requests; DLEN is not the end-to-end bus width or useful bandwidth.')
    fact('scalar-l1-cache-geometry', {str(row['value']['hart_id']):{
         'instruction':row['value']['icache'],'data':row['value']['dcache']} for row in baseline['facts']['harts']},
         [ref('dts','cpu@0 {','cpu@1 {'),ref('dts','cpu@1 {','cpu@2 {'),ref('dts','cpu@2 {','riscv,pmpregions')],
         'DTS capacity/sets/block size plus the source-backed main manifest identify geometry. No hit/miss cycle cost is inferred.')
    fact('actual-tile-and-uncore-beat-bytes', {'shuttle_tile':32,'tcm_bank':32,'scratchpad_bank':8,
         'l2_inner_outer':8,'sbus_tile_master_links':8,'rocket_master':8},
         [graph_ref(node) for node in ('112::0','162::0','311::0','318::0','54::0','128::0','178::0','277::0')],
         'Widths describe identified elaborated TL ports, not simultaneous useful throughput. The optional WithIrisBusTweaks fragment is commented out.')
    l2 = json.loads(texts['l2'])
    if len(l2['banks']) != 4 or any(bank['setBits'] != list(range(8,17)) for bank in l2['banks']):
        raise ValueError('L2 bank layout changed')
    fact('l2-organization', {'capacity_bytes':524288,'banks':4,'ways':4,'sets_per_bank':512,'block_bytes':64,
         'bank_formula':'(address >> 6) & 3','set_formula':'(address >> 8) & 511',
         'subbanks_per_bank':4,'subbank_width_bytes':8,'bank_address_sets':[bank['addresses'] for bank in l2['banks']]},
         [ref('l2','{"banks"')])
    fact('tcm-organization', {'bytes_per_hart':131072,'banks_per_hart':2,'bank_formula':'(address >> 6) & 1',
         'bank_masks': [{'base':0x70000000,'mask':0x1ffbf},{'base':0x70000040,'mask':0x1ffbf}],
         'global_bases':[0x70000000,0x70020000],'bytes_per_bank':65536,'atomics':True},
         [ref('shuttle-tile','for (b <- 0 until tcmParams.banks)','tcm.node := TLFragmenter'), graph_ref('112::0'),graph_ref('115::0')])
    fact('scratchpad-organization', {'base':0x580000000,'size_bytes':131072,'banks':2,'subbanks':1,
         'bank_formula':'(address >> 6) & 1','bank_masks':[{'base':0x580000000,'mask':0x1ffbf},{'base':0x580000040,'mask':0x1ffbf}],
         'bytes_per_bank':65536,'atomics':False,'os_dts_status':'disabled'},
         [ref('iris','new testchipip.soc.WithScratchpad(', 'outerBuffer = BufferParams.default'),
          ref('scratch-config','busWhere: TLBusWrapperLocation = SBUS','subBanks: Int = 1'),
          ref('scratch','val bankStripe =','val mask ='),graph_ref('311::0'),graph_ref('318::0'),ref('dts','memory@580000000','status = "disabled"')])
    fact('lrsc-versus-amo-permissions', {'lr_sc_cacheable_region_required':True,
         'dram_lr_sc':True,'tcm_lr_sc':False,'tcm_private_alias_lr_sc':False,'scratchpad_lr_sc':False,
         'tcm_supported_amo':True,'scratchpad_supported_amo':False,
         'uncached_lr_exception':'load-access-fault','uncached_sc_exception':'store-access-fault'},
         [ref('shuttle-tlb','val cmd_lrsc =','val ae_ld_array ='),ref('rocket-tlb','val lrscAllowed =','val ae_ld_array ='),
          ref('shuttle-pma','io.resp.cacheable :='),graph_ref('112::0'),graph_ref('311::0')],
         'A manager arithmetic/logical-atomic bit does not authorize LR/SC. The core TLB separately requires cacheability (AcquireB support).')
    fact('per-hart-pmp', {'entries':[0,0,8],'rocket_granularity_bytes':4},
         [ref('shuttle-core-params','val nPMPs: Int = 0'),ref('shuttle-tlb','require(nPMPs == 0)'),
          ref('dts','riscv,pmpgranularity = <4>','riscv,pmpregions = <8>')],
         'A single global generic Spike PMP configuration does not reproduce the heterogeneous cores.')
    fact('noc-configuration', {'acd_topology':'bidirectional torus/ring,7routers','be_topology':'unidirectional torus/ring,7routers',
         'acd_vcs_per_link':6,'be_vcs_per_link':4,'buffers_per_vc_flits':5,
         'combineRCVA':True,'combineSAST':True,'ingress_nodes_by_hart':[0,3,5],
         'tcm_egress_nodes':[0,3],'scratchpad_egress_node':1,'l2_egress_node':2},
         [ref('iris','object IrisNoCParams','beDivision = 8'),ref('iris','inNodeMapping = ListMap(', 'inlineNoC = true')],
         'Forward A/C/D routes and B/E coherence routes have distinct resources. Hop counts alone are not latency.')
    fact('crossings', {'shuttle_master_slave':'synchronous TLBuffers','rocket_master_slave':'TLAsyncCrossingSource/Sink',
         'async_handshake_cost_cycles':None},
         [ref('iris','WithAsynchronousShuttleTiles(4, 3, location=InCluster(0))'),ref('shuttle-config','class WithAsynchronousShuttleTiles','case t => t'),
          ref('shuttle-tile','case class ShuttleCrossingParams','forceSeparateClockReset'),graph_ref('128'),graph_ref('178'),graph_ref('277'),graph_ref('278'),graph_ref('281')],
         'The Shuttle fragment targets InCluster(0); these elaborated tiles are InSubsystem. Rocket async hardware remains even when clock frequencies match.')
    fact('clock-domains-local-elaboration', {'harts_hz':[500000000,500000000,500000000],
         'chiptop0_sbus_l2_scratchpad_mbus_hz':500000000,'chiptop1_dram_bus_hz':1000000000,
         'interchip_serial_clock_hz':100000000,'mtime_hz':500000,'fpga_emulation_hz_is_target_frequency':False},
         [ref('fir-clocks','connect clockGroupCombinerOut.member.allClocks_sbus_0','connect clockGroupCombinerOut.member.allClocks_cbus_0'),
          ref('fir-clocks','connect bank.auto.clock_in','connect serial_tl_domain_1.auto.clock_in'),
          ref('fir-clocks','connect chiptop0.clock_uncore','connect chiptop0.clock_tileClockGroup_rockettile_2'),
          ref('fir-clocks','connect chiptop0_clock_uncore_clock, uartSyncClock_clock','connect harnessBinderClk, clock_clock_1'),
          ref('clock-annotation','"clocks": [','"clockMFMRs"'),ref('clocks','Input Reference Frequency'),ref('dts','timebase-frequency = <500000>')],
         'The FIR harness ties the separate Rocket clock input to the same 500MHz source as Iris uncore. This resolves the saved elaboration, not the deployed image association.')
    fact('serial-dram-path', {'iris_port':1,'bringup_port':0,'phit_bits':16,'flit_bits':16,'serial_hz':100000000,
         'dram_endpoint':'chiptop1 AXI4 -> FASEDMemoryTimingModel','axi_data_bits':64,'guest_dram_bytes':0x100000000,
         'fased_kind_from_compiler_config':'LatencyPipeConfig','source_default_read_latency':30,'source_default_write_latency':30,
         'default_latency_unit':'FASED target endpoint clock cycles (1GHz in local elaboration)',
         'selected_remote_read_latency':None,'selected_remote_write_latency':None,'effective_payload_bandwidth_bytes_per_second':None},
         [ref('target','class IrisFiresimConfig','class IrisFiresimBringupConfig'),
          ref('target','DecoupledInternalSyncSerialPhyParams'),ref('target','class IrisFiresimNOCflushCombinedConfig','new chipyard.harness.WithMultiChip(1'),
          ref('compiler-config','class BaseCorigineMimicTurboGTConfig','new midas.CorigineMimicTurboGTConfig'),
          ref('fased-config','class WithDefaultMemModel','new LatencyPipeConfig'),ref('latency-pipe','val registers =','readLatency  -> RuntimeSetting'),
          ref('fased-annotation','"widgetClass": "midas.models.FASEDMemoryTimingModel"','"memoryRegionName"')],
         'Defaults are not measured Iris miss latency. Include cache/refill, NoC, serializers, CDC, buffering and return path. The 8GiB host FPGA capacity is not the 4GiB guest aperture.')
    fact('historical-memory-runtime-overrides', {'historical_success':'2026-11-04--23-20-38-bare',
         'historical_failure':'2026-11-05--04-26-53-bare','mm_plusargs_present':False,
         'remote_current_settings_verified':False},
         [ref('historical-success-argv','screen -S fsim0'),ref('historical-failed-argv','screen -S fsim0'),
          ref('fased-driver','// Find arguments: +mm_','user_configuration[key] = value'),
          ref('fased-driver','if (!user_configuration.empty()) {','auto init_val =')],
         'Saved launch scripts contain no +mm_* overrides. The driver leaves hardware defaults when its user configuration is empty; current image values must be read or matched to build evidence.')
    fact('sram-and-buffer-structural-minima', {'tlram_advertised_min_latency_cycles':1,'tlram_sramReg_default':False,
         'shuttle_icache_configured_latency':2,'complete_cpu_tcm_latency_cycles':None,'complete_cpu_scratchpad_latency_cycles':None},
         [ref('sram','sramReg: Boolean = false'),ref('sram','minLatency = 1'),ref('sram','This block has a three-stage pipeline','When stage D needs to perform a write'),
          ref('buffer','clientFn','managerFn'),ref('shuttle-icache','require(outer.icacheParams.latency == 2)')],
         'Advertised link minima and SRAM pipeline stages are structural bounds in their own domains, not measured load-to-use latency. AMOs, ECC and arbitration may add work.')
    fact('inclusive-cache-outer-latency-meaning', {'configured_outerLatencyCycles':4,'imposed_dram_latency_cycles':None},
         [ref('iris','outerLatencyCycles = 4'),ref('l2-config','memCycles = outerLatencyCycles'),ref('l2-params','// Provision enough resources','val putBeats =')],
         'memCycles sizes resources. It does not delay external memory responses by four cycles or establish DDR timing.')
    fact('serial-load-warning', {'emitted':True,'warning':'DEADLOCKING DECOUPLED SERIAL PHY; heavy load can deadlock'},
         [ref('elaboration-log','WARNING: YOU ARE USING A DEADLOCKING DECOUPLED','DEADLOCK-FREEDOM IS NECESSARY.')],
         'A calibration that only completes light traffic cannot certify saturation/contention regimes; retain timeout/failure evidence and inspect RTL before changing PHY.')

    alias_evidence = [ref('shuttle-tile','def tcmAdjusterNode','def tcmSlaveReplicator'),
                      ref('shuttle-tile','def tcmMasterReplicator','TLFilter(TLFilter.mSubtract'),
                      ref('shuttle-offset','def contains','out.a.bits.address := adjusted'),
                      ref('replication','val replicationMask'),ref('replication','val a_addr','out.a.bits.address :='),
                      graph_ref('94::0'),graph_ref('144::0'),ref('fir-alias','0he0000')]
    aliases = [{'id':'shuttle-private-tcm-aliases','harts':[0,1],'base':0x70080000,'size_bytes':0x80000,
                'mirrors':4,'mirror_size_bytes':0x20000,
                'canonical_storage_formula':'0x70000000 + hart * 0x20000 + (address & 0x1ffff)',
                'permissions':{'read':True,'write':True,'execute':True,'atomics':True},
                'hart2_and_external_access':'not advertised on external SBUS; not a Rocket mapping',
                'evidence':alias_evidence,
                'required_model_behavior':'Alias accesses share storage and supported AMO effects with that hart\'s canonical TCM. Both aliases/canonical TCM reject LR/SC because they are uncached. Preserve original guest address for architectural trap reporting; route timing uses local tile path.'}]

    def hops(start, end):
        forward = (end-start) % 7
        backward = (start-end) % 7
        direction = 1 if forward < backward else -1
        return [(start + direction*i) % 7 for i in range(min(forward,backward)+1)]
    routes=[]
    for hart in range(3):
        for requester in ('instruction','scalar_data','vector_data'):
            for region, target, bank in [('tcm0',0,'(address >> 6) & 1'),('tcm1',3,'(address >> 6) & 1'),
                                          ('scratchpad',1,'(address >> 6) & 1'),('dram',2,'(address >> 6) & 3')]:
                local = region == 'tcm' + str(hart) and hart < 2
                origin = [0,3,5][hart]
                frontend = ('L1I hit or refill' if requester=='instruction' else
                            'scalar L1D for cacheable DRAM; uncached IO path for TCM/scratchpad' if requester=='scalar_data' else
                            'Saturn TLSplitInterface direct TL; no scalar L1D')
                tail = ['tile-local AddressOffsetter/RegionReplicator','TCM bank'] if local else [
                       'tile master/crossing', 'SBUS A/C/D NoC',
                       'target tile slave/crossing -> TCM bank' if region.startswith('tcm') else
                       'SBUS scratchpad bank' if region=='scratchpad' else
                       'L2 bank hit, or MBUS/SerialTL1 -> bringup SerialTL0 -> AXI4/FASED miss']
                routes.append({'id':f'hart{hart}.{requester}.{region}','hart':hart,'requester':requester,'region':region,
                               'frontend':frontend,'miss_or_uncached_path':tail,'scalar_l1d_bypassed':True if requester=='vector_data' else None,
                               'local_tcm_shortcut':local,
                               'acd_request_router_path':[] if local else hops(origin,target),
                               'acd_response_router_path':[] if local else hops(target,origin),
                               'be_coherence_network':'unidirectional torus; only when the transaction requires coherence',
                               'bank_selection':bank,'requester_clock_hz':500000000,'fitted_latency_cycles':None,
                               'evidence':[ref('shuttle-tile','val frontend =','val tcmSlaveXbar'),
                                           ref('saturn-rocket','val load_use_tl_reg =','val store_use_tl ='),
                                           ref('fir-clocks','connect chiptop0.clock_uncore','connect chiptop0.clock_tileClockGroup_rockettile_2'),
                                           ref('iris','inNodeMapping = ListMap(', 'inlineNoC = true'),
                                           ref('target','class IrisFiresimNOCflushCombinedConfig','new chipyard.harness.WithMultiChip(1')]})

    v1=json.loads((WORKSPACE/'benchmarks/calibration-corpus.json').read_text())
    v2=json.loads((WORKSPACE/'benchmarks/v2/corpus.json').read_text())
    ids=[row['case_id'] for row in v1['cases']+v2['cases']]
    probes=[]
    def probe(identity, patterns, isolates, gaps):
        selected=[case for case in ids if any(re.search(pattern,case) for pattern in patterns)]
        probes.append({'id':identity,'existing_case_ids':selected,'helps_identify':isolates,'remaining_isolation_gaps':gaps,
                       'ground_truth_collected':False,'evidence':[ref('iris','new testchipip.soc.WithScratchpad(', 'outerBuffer = BufferParams.default'),ref('l2','{"banks"')]})
    probe('tcm-local-and-remote', [r'^memory\.tcm\.'], ['source baseline local compute-hart TCM loop'],
          ['Explicit remote TCM per requester/hart, pointer chains, read/write/AMO separation, same-bank vs separate-bank, alias/canonical equivalence, all-three contention'])
    probe('scratchpad', [r'^memory\.scratchpad\.'], ['all-hart uncached scratchpad scalar loops'],
          ['Dependent-load latency, scalar/vector widths, exact bit6 bank conflicts, saturation and read/write mixes; no scratchpad AMOs'])
    probe('cache-capacity-and-misses', [r'^v2\.memory\.',r'^memory\.(dram|pointer)\.'],
          ['warm/eviction-attempt sizes and scalar dependency chains'],
          ['Source replacement/coherence verification, exact L1/L2 hit identification, targeted L2 set/bank aliases, vector bypass controls, TLB/PTW state'])
    probe('shared-contention', [r'^v2\.contention\.'], ['all seven hart subsets, shared/private reads, atomic false sharing, hart2 vector writer'],
          ['Dedicated same/different L2 bank sweeps, NoC route conflicts, in-flight queue occupancy, serial-TL saturation, directional load/store traffic'])
    probe('instruction-frontends', [r'^v2\.frontend\.'], ['exact instruction footprints and reuse'],
          ['I-cache miss-path counters, executable TCM/scratchpad tests by every hart, branch/frontend separation'])
    probe('distributed-pipelines', [r'^v2\.pipeline\.'], ['producer/vector-compute/consumer rotations and VME pipelines with hart2 producer'],
          ['Zephyr runtime overhead and preemption, real overlap/traces, link-heavy saturation and deadlock observation'])
    data={'schema_version':1,'scope':'local-elaboration-memory-path-audit','calibrated':False,
          'generator_sha256':sha(Path(__file__)),
          'deployed_image_association_verified':False,'hardware_manifest_sha256':sha(HERE/'manifest.json'),
          'repositories':repositories,'sources':sources,'facts':facts,'routes':routes,'local_aliases':aliases,
          'calibration_probes':probes,'benchmark_input_sha256':{
              'benchmarks/calibration-corpus.json':sha(WORKSPACE/'benchmarks/calibration-corpus.json'),
              'benchmarks/v2/cases.py':sha(WORKSPACE/'benchmarks/v2/cases.py')},
          'unmeasured_timing_parameters':{key:None for key in ['cpu_l1_hit_and_miss_load_to_use','scalar_uncached_tcm','remote_tcm',
              'scratchpad_read_write','l2_hit_and_replacement','l2_bank_and_subbank_contention','noc_router_hop_and_arbitration',
              'serial_transaction_latency','serial_useful_payload_bandwidth','selected_fased_runtime_registers',
              'cdc_queue_round_trip','vector_memory_expansion_and_overlap','zephyr_interrupt_and_scheduler_interference']},
          'limitations':['No actual FPGA/RTL reference runs were collected by this audit.',
              'Clock/geometry/route facts describe the identified local elaboration, not proven deployed image build inputs.',
              'No link minimum, static width, source sizing hint or source runtime default is promoted to a calibrated CPU latency.',
              'Cache hit/miss choice, arbitration, coherence, vector requests and queue/clock state still require an integrated model and validation.']}
    validate(data)
    (HERE/'memory-paths.json').write_text(json.dumps(data,indent=2)+'\n')
    return data


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--verify-live',action='store_true')
    args=parser.parse_args()
    data=json.loads((HERE/'memory-paths.json').read_text()) if args.verify or args.verify_live else generate(args.root)
    print(json.dumps(validate(data,args.root if args.verify_live else None),indent=2))


if __name__=='__main__': main()
