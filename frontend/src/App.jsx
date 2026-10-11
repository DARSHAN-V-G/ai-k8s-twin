import { useState, useRef, useEffect, useMemo } from 'react'
import './App.css'

const CHAOS_ENVIRONMENTS = [
  ['Pod Kill', 'pod-kill', 'Terminate workload pod and observe recovery.'],
  ['CPU Stress', 'cpu-stress', 'Saturate processor capacity.'],
  ['Memory Stress', 'memory-stress', 'Apply container memory pressure.'],
  ['Network Delay', 'network-delay', 'Inject latency between microservices.'],
  ['Network Loss', 'network-loss', 'Drop packets and measure error retries.'],
  ['Network Partition', 'network-partition', 'Isolate service communications.'],
  ['Node Failure', 'node-failure', 'Simulate underlying Kubernetes node outage.'],
]

const STAGE_KEYS = [
  { key: 'deploy', label: 'Deploy' },
  { key: 'pod_kill', label: 'Pod Kill' },
  { key: 'five_chaos', label: '5-Chaos' },
  { key: 'node_failure', label: 'Node Fail' },
]

const DEFAULT_FORM = {
  github_url: 'https://github.com/GoogleCloudPlatform/microservices-demo.git',
  cpu: '2',
  memory: '4Gi',
  vus: '10',
  duration: '30s',
  mode: 'binary_search',
}

function App() {
  const [form, setForm] = useState(DEFAULT_FORM)
  const [selectedEnvironments, setSelectedEnvironments] = useState(
    CHAOS_ENVIRONMENTS.map(([name]) => name)
  )
  const [running, setRunning] = useState(false)
  const [activeRunningService, setActiveRunningService] = useState(null)
  const [configCollapsed, setConfigCollapsed] = useState(false)

  // Service-wise state: list of services: { name, namespace, kind, status, stages: {}, optimization, metrics, error }
  const [services, setServices] = useState([])
  const [selectedServiceName, setSelectedServiceName] = useState(null)
  const [serviceFilter, setServiceFilter] = useState('all') // 'all' | 'running' | 'passed' | 'failed'

  // Logs state: all logs, plus per-service partitioned logs
  const [globalLogs, setGlobalLogs] = useState([
    { type: 'info', text: 'Console ready. Configure workload and run resilience orchestrator.' },
  ])
  const [serviceLogs, setServiceLogs] = useState({}) // { [serviceName]: [{type, text}] }
  const [activeLogTab, setActiveLogTab] = useState('service') // 'service' | 'all'
  const [logFilterQuery, setLogFilterQuery] = useState('')

  const [autoScroll, setAutoScroll] = useState(true)
  const [copiedServiceYaml, setCopiedServiceYaml] = useState(false)
  const isUserInspectingRef = useRef(false)
  const controllerRef = useRef(null)
  const terminalBottomRef = useRef(null)

  const handleCopyYaml = (yamlText) => {
    if (!yamlText) return
    navigator.clipboard.writeText(yamlText)
    setCopiedServiceYaml(true)
    setTimeout(() => setCopiedServiceYaml(false), 2000)
  }

  const handleDownloadYaml = (serviceName, yamlText) => {
    if (!yamlText) return
    const blob = new Blob([yamlText], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${serviceName || 'service'}-optimized-deployment.yaml`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const generateFallbackYaml = (svc) => {
    if (!svc) return ''
    const memLimit = svc.optimization?.recommended_config?.memory_limit || '32Mi'
    const memReq = svc.optimization?.recommended_config?.memory_request || '18Mi'
    const cpuLimit = svc.optimization?.recommended_config?.cpu_limit || '62m'
    const cpuReq = svc.optimization?.recommended_config?.cpu_request || '25m'
    return `apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${svc.name}
  namespace: ${svc.namespace || 'default'}
  labels:
    app: ${svc.name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${svc.name}
  template:
    metadata:
      labels:
        app: ${svc.name}
    spec:
      containers:
        - name: server
          image: ${svc.name}
          resources:
            requests:
              cpu: ${cpuReq}
              memory: ${memReq}
            limits:
              cpu: ${cpuLimit}
              memory: ${memLimit}
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            timeoutSeconds: 2`
  }

  const addLogEntry = (serviceName, type, text) => {
    const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0)
    if (lines.length === 0) return

    setGlobalLogs((prev) => [
      ...prev,
      ...lines.map((line) => ({ type, text: line, service: serviceName })),
    ])

    if (serviceName) {
      setServiceLogs((prev) => ({
        ...prev,
        [serviceName]: [
          ...(prev[serviceName] || []),
          ...lines.map((line) => ({ type, text: line })),
        ],
      }))
    }
  }

  const updateField = (e) => {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const toggleEnvironment = (name) => {
    setSelectedEnvironments((prev) =>
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
    )
  }

  const stopExperiment = async () => {
    addLogEntry(null, 'command', '$ POST /api/environment-orchestrator/stop')
    try {
      await fetch('/api/environment-orchestrator/stop', { method: 'POST' })
    } catch (e) {
      console.error('Stop request error:', e)
    }
    if (controllerRef.current) {
      controllerRef.current.abort()
      controllerRef.current = null
    }
    setRunning(false)
    setActiveRunningService(null)
    setServices((prev) =>
      prev.map((s) => (s.status === 'running' ? { ...s, status: 'waiting' } : s))
    )
  }

  const executeOrchestrator = async (targetService = null) => {
    // If an execution is running, abort it cleanly first
    if (running || controllerRef.current) {
      await stopExperiment()
      await new Promise((r) => setTimeout(r, 120))
    }

    setRunning(true)
    setConfigCollapsed(true)
    setActiveRunningService(targetService && targetService !== 'discovery_only' ? targetService : null)

    if (targetService && targetService !== 'discovery_only') {
      // Running a specific service: mark only this service as running
      setServices((prev) =>
        prev.map((s) =>
          s.name === targetService
            ? {
                ...s,
                status: 'running',
                iterations: [],
                optimization: null,
                stages: {
                  deploy: 'pending',
                  pod_kill: 'pending',
                  five_chaos: 'pending',
                  node_failure: 'pending',
                },
                error: null,
              }
            : s
        )
      )
      setSelectedServiceName(targetService)
      isUserInspectingRef.current = true
    } else if (!targetService) {
      // Running all: reset all services to waiting
      setServices((prev) =>
        prev.map((s) => ({
          ...s,
          status: 'waiting',
          iterations: [],
          optimization: null,
          stages: {
            deploy: 'pending',
            pod_kill: 'pending',
            five_chaos: 'pending',
            node_failure: 'pending',
          },
          error: null,
        }))
      )
    }

    controllerRef.current = new AbortController()
    const logTag = targetService === 'discovery_only'
      ? '$ POST /api/environment-orchestrator/run [mode=discovery_only]'
      : targetService
      ? `$ POST /api/environment-orchestrator/run [target_service=${targetService}]`
      : '$ POST /api/environment-orchestrator/run [all_workloads]'
    addLogEntry(targetService, 'command', logTag)

    try {
      const response = await fetch('/api/environment-orchestrator/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          environments: selectedEnvironments,
          ...(targetService ? { target_service: targetService } : {}),
        }),
        signal: controllerRef.current.signal,
      })

      if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}`)
      if (!response.body) throw new Error('Backend did not return an SSE stream')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const messages = buffer.split('\n\n')
        buffer = messages.pop() || ''

        messages.forEach((msg) => {
          if (!msg.trim()) return
          const lines = msg.split('\n')
          const eventLine = lines.find((l) => l.startsWith('event: '))
          const dataLine = lines.find((l) => l.startsWith('data: '))
          const event = eventLine ? eventLine.slice(7).trim() : 'output'
          if (!dataLine) return

          let payload
          try {
            payload = JSON.parse(dataLine.slice(6).trim())
          } catch {
            return
          }

          if (event === 'discovery') {
            const discovered = (payload.services || []).map((s) => ({
              name: s.name,
              namespace: s.namespace || 'default',
              kind: s.kind || 'Deployment',
              status: s.name === targetService ? 'running' : 'waiting',
              stages: {
                deploy: 'pending',
                pod_kill: 'pending',
                five_chaos: 'pending',
                node_failure: 'pending',
              },
              optimization: null,
              metrics: null,
              error: null,
              iterations: [],
            }))

            setServices((prev) => {
              if (prev.length === 0) return discovered
              return discovered.map((d) => {
                const existing = prev.find((p) => p.name === d.name)
                if (!existing) return d
                if (d.name === targetService) {
                  return { ...existing, status: 'running', error: null }
                }
                return existing
              })
            })

            setSelectedServiceName((prev) => prev || discovered[0]?.name || null)
            addLogEntry(
              null,
              'success',
              `Discovered ${discovered.length} microservices in target repository.`
            )
          } else if (event === 'service_start') {
            const svcName = payload.service
            setActiveRunningService(svcName)
            setServices((prev) =>
              prev.map((s) => (s.name === svcName ? { ...s, status: 'running' } : s))
            )
            if (!isUserInspectingRef.current) {
              setSelectedServiceName(svcName)
            }
            addLogEntry(
              svcName,
              'command',
              `[START] Resilience simulation for ${svcName} (${payload.index}/${payload.total})`
            )
          } else if (event === 'stage_update') {
            const { service: svcName, stage, status } = payload
            setServices((prev) =>
              prev.map((s) =>
                s.name === svcName
                  ? {
                      ...s,
                      stages: {
                        ...s.stages,
                        [stage]: status,
                      },
                    }
                  : s
              )
            )
          } else if (event === 'iteration_update') {
            const svcName = payload.service
            setServices((prev) =>
              prev.map((s) => {
                if (s.name !== svcName) return s
                const existing = s.iterations || []
                const filtered = existing.filter((it) => it.iteration !== payload.iteration)
                const updated = [...filtered, payload].sort((a, b) => a.iteration - b.iteration)
                return {
                  ...s,
                  iterations: updated,
                }
              })
            )
            addLogEntry(
              svcName,
              payload.sla_passed ? 'success' : 'error',
              `[TRIAL ${payload.iteration}/${payload.max_iterations}] ${payload.parameter} @ ${payload.tested_value} -> ${
                payload.sla_passed ? 'PASSED' : 'BREACHED'
              } | ${payload.step_taken}`
            )
          } else if (event === 'service_log') {
            addLogEntry(payload.service, 'info', payload.text)
          } else if (event === 'service_result') {
            const svcName = payload.service
            const isPassed = payload.status === 'passed'
            setServices((prev) =>
              prev.map((s) =>
                s.name === svcName
                  ? {
                      ...s,
                      status: isPassed ? 'passed' : 'failed',
                      optimization: payload.optimization,
                      iterations: payload.optimization?.iterations || s.iterations || [],
                      metrics: payload.metrics,
                      error: payload.error,
                      stages: isPassed
                        ? {
                            deploy: 'completed',
                            pod_kill: 'completed',
                            five_chaos: 'completed',
                            node_failure: 'completed',
                          }
                        : s.stages,
                    }
                  : s
              )
            )
            addLogEntry(
              svcName,
              isPassed ? 'success' : 'error',
              isPassed
                ? `[COMPLETED] Service ${svcName} passed resilience evaluation.`
                : `[FAILED] Service ${svcName} failed: ${payload.error || 'Execution failure'}`
            )
          } else if (event === 'aggregate_complete') {
            addLogEntry(null, 'success', '==================================================')
            addLogEntry(
              null,
              'success',
              `Workload evaluation completed (${payload.total} services evaluated).`
            )
            addLogEntry(null, 'success', '==================================================')
          } else if (event === 'error') {
            addLogEntry(null, 'error', `Environment simulation failed: ${payload.message}`)
          }
        })
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        addLogEntry(null, 'error', `Execution error: ${err.message}`)
      }
    } finally {
      controllerRef.current = null
      setRunning(false)
      setActiveRunningService(null)
    }
  }

  const runExperiment = async (e) => {
    e.preventDefault()
    if (running) return
    await executeOrchestrator(null)
  }

  // Active inspected service details
  const activeService = useMemo(
    () => services.find((s) => s.name === selectedServiceName) || services[0] || null,
    [services, selectedServiceName]
  )

  // Filtered services for left sidebar list
  const filteredServices = useMemo(() => {
    if (serviceFilter === 'all') return services
    return services.filter((s) => s.status === serviceFilter)
  }, [services, serviceFilter])

  // Count aggregates
  const counts = useMemo(() => {
    const total = services.length
    const passed = services.filter((s) => s.status === 'passed').length
    const failed = services.filter((s) => s.status === 'failed').length
    const runningCount = services.filter((s) => s.status === 'running').length
    const waiting = services.filter((s) => s.status === 'waiting').length
    return { total, passed, failed, runningCount, waiting }
  }, [services])

  // Logs to show based on tab
  const displayedLogs = useMemo(() => {
    let source = []
    if (activeLogTab === 'service') {
      source = (activeService && serviceLogs[activeService.name]) || []
    } else {
      source = globalLogs
    }
    if (!logFilterQuery.trim()) return source
    const query = logFilterQuery.toLowerCase()
    return source.filter((item) => item.text.toLowerCase().includes(query))
  }, [activeLogTab, activeService, serviceLogs, globalLogs, logFilterQuery])

  // Auto-scroll terminal when new logs arrive, ONLY for currently running service or global console
  useEffect(() => {
    if (!autoScroll || !terminalBottomRef.current) return

    // If viewing a specific service, only scroll if that service is actively running
    if (activeLogTab === 'service') {
      if (activeService && activeService.status === 'running') {
        terminalBottomRef.current.scrollIntoView({ behavior: 'smooth' })
      }
    } else {
      // If viewing global console, scroll down when new logs arrive
      terminalBottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [displayedLogs.length, activeLogTab, activeService?.status, autoScroll])

  return (
    <main className="app-shell">
      {/* Topbar */}
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">AK</div>
          <div>
            <strong>AI K8s Twin</strong>
            <span>Microservice Resilience &amp; Right-Sizing Engine</span>
          </div>
        </div>
        <div className="connection">
          <span className={`pulse ${running ? 'pulse-active' : ''}`} />
          LOCAL MINIKUBE <b>{running ? 'SIMULATING' : 'READY'}</b>
        </div>
      </header>

      {/* Hero Intro */}
      <section className="intro">
        <div>
          <p className="eyebrow">RESILIENCE DASHBOARD / v0.2</p>
          <h1>
            Chaos, made <em>service-aware.</em>
          </h1>
          <p className="lede">
            Discover all Kubernetes microservices in your repo, run compound chaos sequences, and
            isolate per-service self-healing performance with right-sizing recommendations.
          </p>
        </div>
        <div className="intro-stats">
          <div className="stat-box">
            <span>DISCOVERED</span>
            <strong>{counts.total}</strong>
            <small>Workloads</small>
          </div>
          <div className="stat-box">
            <span>PASSED SLA</span>
            <strong className="stat-green">{counts.passed}</strong>
            <small>Services</small>
          </div>
        </div>
      </section>

      {/* Collapsible Run Configuration Panel */}
      <section className="panel config-panel">
        <div
          className="panel-heading config-heading"
          onClick={() => setConfigCollapsed(!configCollapsed)}
          style={{ cursor: 'pointer' }}
        >
          <div>
            <span className="section-number">01</span>
            <h2>Run Configuration &amp; Chaos Pipeline</h2>
          </div>
          <div className="config-heading-right">
            <span className="count-label">{selectedEnvironments.length} chaos environments</span>
            <button
              type="button"
              className="toggle-config-btn"
              onClick={(e) => {
                e.stopPropagation()
                setConfigCollapsed(!configCollapsed)
              }}
            >
              {configCollapsed ? '▼ Expand Settings' : '▲ Collapse Settings'}
            </button>
          </div>
        </div>

        {!configCollapsed && (
          <form className="config-form" onSubmit={runExperiment}>
            <div className="form-group">
              <label>
                GitHub Repository URL
                <div className="input-with-action">
                  <input
                    name="github_url"
                    value={form.github_url}
                    onChange={updateField}
                    placeholder="https://github.com/org/repository"
                    required
                  />
                  <button
                    type="button"
                    className="quick-sample-btn"
                    onClick={() =>
                      setForm((prev) => ({
                        ...prev,
                        github_url:
                          'https://github.com/GoogleCloudPlatform/microservices-demo.git',
                      }))
                    }
                  >
                    Google Microservices Demo
                  </button>
                </div>
              </label>
            </div>

            <div className="input-grid">
              <label>
                Available CPU
                <input name="cpu" value={form.cpu} onChange={updateField} required />
              </label>
              <label>
                Available Memory
                <input name="memory" value={form.memory} onChange={updateField} required />
              </label>
              <label>
                k6 VUs
                <input
                  name="vus"
                  type="number"
                  min="1"
                  value={form.vus}
                  onChange={updateField}
                  required
                />
              </label>
              <label>
                Duration
                <input name="duration" value={form.duration} onChange={updateField} required />
              </label>
            </div>

            <div className="form-group mode-select-group">
              <label>
                Optimization Strategy
                <select name="mode" value={form.mode} onChange={updateField}>
                  <option value="binary_search">
                    Binary Search Optimizer (Auto-Tune &amp; Right-Sizing Limits)
                  </option>
                  <option value="heuristic">Heuristic Single-Run (Fast Deterministic)</option>
                </select>
              </label>
            </div>

            <div className="environment-selection">
              <span className="env-title">Select Chaos Sequence:</span>
              <div className="environment-options">
                {CHAOS_ENVIRONMENTS.map(([name, shortName, description]) => (
                  <label className="environment-option" key={name}>
                    <input
                      type="checkbox"
                      checked={selectedEnvironments.includes(name)}
                      onChange={() => toggleEnvironment(name)}
                    />
                    <span>
                      <strong>{name}</strong>
                      <small>{description}</small>
                    </span>
                    <code>{shortName}.yaml</code>
                  </label>
                ))}
              </div>
            </div>

            <div className="run-actions">
              <button
                className="run-button"
                type="submit"
                disabled={running || selectedEnvironments.length === 0}
              >
                <span>
                  {running ? 'Execution In Progress...' : 'Run All Workloads'}
                </span>
                <b>{running ? '[BUSY]' : '->'}</b>
              </button>

              <button
                className="discover-button"
                type="button"
                disabled={running}
                onClick={() => executeOrchestrator('discovery_only')}
                title="Clone and scan manifests to discover all microservices"
              >
                Discover Workloads
              </button>

              {running && (
                <button className="stop-button" type="button" onClick={stopExperiment}>
                  Stop Execution <b>[X]</b>
                </button>
              )}
            </div>
          </form>
        )}
      </section>

      {/* Aggregate Progress Overview Bar */}
      {services.length > 0 && (
        <section className="overview-strip">
          <div className="overview-counts">
            <span className="overview-label">Workload Progress:</span>
            <span className="badge badge-neutral">Total: {counts.total}</span>
            <span className="badge badge-running">Running: {counts.runningCount}</span>
            <span className="badge badge-passed">Passed: {counts.passed}</span>
            <span className="badge badge-failed">Failed: {counts.failed}</span>
            <span className="badge badge-waiting">Queued: {counts.waiting}</span>
          </div>

          <div className="filter-tabs">
            <span>Filter:</span>
            {['all', 'running', 'passed', 'failed'].map((f) => (
              <button
                key={f}
                type="button"
                className={`filter-btn ${serviceFilter === f ? 'active' : ''}`}
                onClick={() => setServiceFilter(f)}
              >
                {f.toUpperCase()}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Main Service-Wise Grid & Inspector Layout */}
      <div className="dashboard-grid">
        {/* Left Column: Microservice Cards */}
        <section className="services-column panel">
          <div className="panel-heading">
            <div>
              <span className="section-number">02</span>
              <h2>Microservice Resilience Grid</h2>
            </div>
            <span className="count-label">
              {filteredServices.length} / {services.length} shown
            </span>
          </div>

          {services.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">[CLUSTER]</div>
              <h3>No Workloads Discovered Yet</h3>
              <p>
                Click <strong>"Discover Workloads"</strong> above to scan your repository manifests,
                or launch <strong>"Run All Workloads"</strong> to discover and evaluate all microservices.
              </p>
            </div>
          ) : (
            <div className="services-list">
              {filteredServices.map((svc) => {
                const isSelected = selectedServiceName === svc.name
                const hasOptimization = Boolean(svc.optimization)
                const recMem = svc.optimization?.recommended_config?.memory_limit
                const recCpu = svc.optimization?.recommended_config?.cpu_limit

                return (
                  <div
                    key={svc.name}
                    className={`service-card ${isSelected ? 'is-selected' : ''} status-${svc.status}`}
                    onClick={() => {
                      isUserInspectingRef.current = true
                      setSelectedServiceName(svc.name)
                    }}
                  >
                    <div className="card-top">
                      <div className="card-identity">
                        <strong>{svc.name}</strong>
                        <span className="card-meta">
                          {svc.kind} • {svc.namespace}
                        </span>
                      </div>
                      <div className="card-actions-group">
                        <span className={`status-pill pill-${svc.status}`}>
                          {svc.status === 'running' && <span className="spinner" />}
                          {svc.status.toUpperCase()}
                        </span>
                        {svc.status === 'running' ? (
                          <button
                            type="button"
                            className="btn-card-action btn-card-stop"
                            onClick={(e) => {
                              e.stopPropagation()
                              stopExperiment()
                            }}
                            title={`Stop ${svc.name}`}
                          >
                            STOP
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn-card-action btn-card-run"
                            onClick={(e) => {
                              e.stopPropagation()
                              executeOrchestrator(svc.name)
                            }}
                            title={running ? `Stop current and run ${svc.name}` : `Run ${svc.name}`}
                          >
                            RUN
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Stage Pipeline Chips */}
                    <div className="stages-pipeline">
                      {STAGE_KEYS.map(({ key, label }) => {
                        const stageStatus = svc.stages[key] || 'pending'
                        return (
                          <div key={key} className={`stage-step step-${stageStatus}`} title={`${label}: ${stageStatus}`}>
                            <span className="step-dot">
                              {stageStatus === 'completed'
                                ? '[OK]'
                                : stageStatus === 'failed'
                                ? '[X]'
                                : stageStatus === 'running'
                                ? '[..]'
                                : '[-]'}
                            </span>
                            <span className="step-label">{label}</span>
                          </div>
                        )
                      })}
                    </div>

                    {/* Sizing recommendation teaser */}
                    {hasOptimization && (
                      <div className="sizing-teaser">
                        <span className="sizing-tag">Right-Sized:</span>
                        <code>
                          {recMem}
                          {svc.optimization?.recommended_config?.memory_request
                            ? ` / ${svc.optimization.recommended_config.memory_request}`
                            : ''}{' '}
                          RAM • {recCpu}
                          {svc.optimization?.recommended_config?.cpu_request
                            ? ` / ${svc.optimization.recommended_config.cpu_request}`
                            : ''}{' '}
                          CPU
                        </code>
                      </div>
                    )}

                    {/* Iteration Count & Safe Tolerance Tag */}
                    {(svc.iterations?.length > 0 || svc.optimization?.iterations?.length > 0) && (
                      <div className="iterations-card-badge">
                        <span className="iter-count-tag">
                          ITERATIONS: {(svc.iterations || svc.optimization?.iterations || []).length}
                        </span>
                        {svc.optimization?.optimal_values ? (
                          <span className="safe-tol-tag">
                            SAFE: <code>RAM {svc.optimization.optimal_values.RAM} • LOSS {svc.optimization.optimal_values.LOSS}</code>
                          </span>
                        ) : svc.optimization?.max_safe_tolerance ? (
                          <span className="safe-tol-tag">
                            SAFE: <code>{svc.optimization.max_safe_tolerance}</code>
                          </span>
                        ) : null}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </section>

        {/* Right Column: Service Inspector & Logs */}
        <section className="inspector-column panel">
          <div className="panel-heading">
            <div>
              <span className="section-number">03</span>
              <h2>Workload Inspector &amp; Telemetry</h2>
            </div>
            {activeService && (
              <span className="active-service-tag">{activeService.name}</span>
            )}
          </div>

          {activeService ? (
            <div className="inspector-body">
              {/* Service Header & Sizing Card */}
              <div className="inspector-summary-card">
                <div className="inspector-header">
                  <div>
                    <h3>{activeService.name}</h3>
                    <p className="service-sub">
                      Namespace: <code>{activeService.namespace}</code> | Kind:{' '}
                      <code>{activeService.kind}</code>
                    </p>
                  </div>
                  <div className="inspector-ctrl-group">
                    <span className={`status-pill pill-${activeService.status}`}>
                      {activeService.status === 'running' && <span className="spinner" />}
                      {activeService.status.toUpperCase()}
                    </span>

                    {activeService.status === 'running' ? (
                      <button
                        type="button"
                        className="btn-inspector-action btn-inspector-stop"
                        onClick={stopExperiment}
                      >
                        STOP SERVICE
                      </button>
                    ) : running && activeRunningService && activeRunningService !== activeService.name ? (
                      <div className="switch-action-row">
                        <button
                          type="button"
                          className="btn-inspector-action btn-inspector-run"
                          onClick={() => executeOrchestrator(activeService.name)}
                          title={`Stop ${activeRunningService} and execute ${activeService.name}`}
                        >
                          SWITCH &amp; RUN THIS SERVICE
                        </button>
                        <button
                          type="button"
                          className="btn-inspector-action btn-inspector-stop-alt"
                          onClick={stopExperiment}
                          title={`Stop ${activeRunningService}`}
                        >
                          STOP {activeRunningService.toUpperCase()}
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="btn-inspector-action btn-inspector-run"
                        onClick={() => executeOrchestrator(activeService.name)}
                      >
                        RUN THIS SERVICE
                      </button>
                    )}
                  </div>
                </div>

                {/* Resilience & Right-Sizing Insights */}
                {activeService.optimization ? (
                  <div className="optimization-insights">
                    <div
                      className={`sla-banner ${
                        activeService.optimization.sla_passed ? 'sla-pass' : 'sla-fail'
                      }`}
                    >
                      <span className="sla-icon">
                        {activeService.optimization.sla_passed ? '[PASS]' : '[BREACH]'}
                      </span>
                      <div>
                        <strong>
                          SLA Verdict:{' '}
                          {activeService.optimization.sla_passed ? 'PASSED' : 'BREACHED'}
                        </strong>
                        <p>{activeService.optimization.sla_verdict}</p>
                      </div>
                    </div>

                    {/* 4-Parameter Resilience Profile Grid */}
                    <div className="multi-param-tolerances-grid">
                      {/* RAM */}
                      <div className={`param-tolerance-card ${activeService.optimization.optimal_values ? 'param-converged' : ''}`}>
                        <div className="param-card-header">
                          <span className="param-title">RAM STRESS</span>
                          <span className={`param-status-pill ${activeService.optimization.optimal_values ? 'pill-converged' : 'pill-active'}`}>
                            {activeService.optimization.optimal_values ? '[CONVERGED]' : '[TUNING]'}
                          </span>
                        </div>
                        <div className="param-card-value">
                          {activeService.optimization.optimal_values?.RAM || activeService.optimization.max_safe_tolerance || 'N/A'}
                        </div>
                        <div className="param-card-bounds">
                          <span className="bounds-label">Active Bounds:</span>
                          <code>[{activeService.optimization.bounds?.['Memory Stress']?.low || 1}M, {activeService.optimization.bounds?.['Memory Stress']?.high || 128}M]</code>
                        </div>
                      </div>

                      {/* CPU */}
                      <div className={`param-tolerance-card ${activeService.optimization.optimal_values ? 'param-converged' : ''}`}>
                        <div className="param-card-header">
                          <span className="param-title">CPU SATURATION</span>
                          <span className={`param-status-pill ${activeService.optimization.optimal_values ? 'pill-converged' : 'pill-active'}`}>
                            {activeService.optimization.optimal_values ? '[CONVERGED]' : '[TUNING]'}
                          </span>
                        </div>
                        <div className="param-card-value">
                          {activeService.optimization.optimal_values?.CPU || '50%'}
                        </div>
                        <div className="param-card-bounds">
                          <span className="bounds-label">Active Bounds:</span>
                          <code>[{activeService.optimization.bounds?.['CPU Stress']?.low || 10}%, {activeService.optimization.bounds?.['CPU Stress']?.high || 100}%]</code>
                        </div>
                      </div>

                      {/* DELAY */}
                      <div className={`param-tolerance-card ${activeService.optimization.optimal_values ? 'param-converged' : ''}`}>
                        <div className="param-card-header">
                          <span className="param-title">NETWORK DELAY</span>
                          <span className={`param-status-pill ${activeService.optimization.optimal_values ? 'pill-converged' : 'pill-active'}`}>
                            {activeService.optimization.optimal_values ? '[CONVERGED]' : '[TUNING]'}
                          </span>
                        </div>
                        <div className="param-card-value">
                          {activeService.optimization.optimal_values?.DELAY || '100ms'}
                        </div>
                        <div className="param-card-bounds">
                          <span className="bounds-label">Active Bounds:</span>
                          <code>[{activeService.optimization.bounds?.['Network Delay']?.low || 10}ms, {activeService.optimization.bounds?.['Network Delay']?.high || 1500}ms]</code>
                        </div>
                      </div>

                      {/* LOSS */}
                      <div className={`param-tolerance-card ${activeService.optimization.optimal_values ? 'param-converged' : ''}`}>
                        <div className="param-card-header">
                          <span className="param-title">PACKET LOSS</span>
                          <span className={`param-status-pill ${activeService.optimization.optimal_values ? 'pill-converged' : 'pill-active'}`}>
                            {activeService.optimization.optimal_values ? '[CONVERGED]' : '[TUNING]'}
                          </span>
                        </div>
                        <div className="param-card-value">
                          {activeService.optimization.optimal_values?.LOSS || '3.0%'}
                        </div>
                        <div className="param-card-bounds">
                          <span className="bounds-label">Active Bounds:</span>
                          <code>[{activeService.optimization.bounds?.['Network Loss']?.low || 0.5}%, {activeService.optimization.bounds?.['Network Loss']?.high || 15.0}%]</code>
                        </div>
                      </div>
                    </div>

                    <div className="sizing-comparison-grid">
                      <div className="sizing-box">
                        <span className="box-title">Memory Allocation</span>
                        <div className="sizing-dual-values">
                          <div className="sizing-val-item">
                            <span className="sub-tag">LIMIT:</span>
                            <strong className="box-value highlight-val">
                              {activeService.optimization.recommended_config?.memory_limit || 'N/A'}
                            </strong>
                          </div>
                          <div className="sizing-val-item">
                            <span className="sub-tag">REQUEST:</span>
                            <strong className="box-value highlight-secondary">
                              {activeService.optimization.recommended_config?.memory_request || 'N/A'}
                            </strong>
                          </div>
                        </div>
                        <small>Limit: +25% buffer • Request: baseline</small>
                      </div>

                      <div className="sizing-box">
                        <span className="box-title">CPU Allocation</span>
                        <div className="sizing-dual-values">
                          <div className="sizing-val-item">
                            <span className="sub-tag">LIMIT:</span>
                            <strong className="box-value highlight-val">
                              {activeService.optimization.recommended_config?.cpu_limit || 'N/A'}
                            </strong>
                          </div>
                          <div className="sizing-val-item">
                            <span className="sub-tag">REQUEST:</span>
                            <strong className="box-value highlight-secondary">
                              {activeService.optimization.recommended_config?.cpu_request || 'N/A'}
                            </strong>
                          </div>
                        </div>
                        <small>Limit: +25% buffer • Request: baseline</small>
                      </div>

                      <div className="sizing-box">
                        <span className="box-title">Max Memory Observed</span>
                        <strong className="box-value">
                          {activeService.metrics?.memory_max
                            ? `${Math.round(activeService.metrics.memory_max / (1024 * 1024))} MiB`
                            : 'N/A'}
                        </strong>
                        <small>During compound chaos</small>
                      </div>
                      <div className="sizing-box">
                        <span className="box-title">Max CPU Observed</span>
                        <strong className="box-value">
                          {activeService.metrics?.cpu_max
                            ? `${(activeService.metrics.cpu_max * 1000).toFixed(0)}m`
                            : 'N/A'}
                        </strong>
                        <small>During compound chaos</small>
                      </div>

                      {/* Optimized Kubernetes Deployment Manifest Panel */}
                      <div className="manifest-export-card">
                        <div className="manifest-export-header">
                          <div className="manifest-title-group">
                            <span className="indicator-pip" />
                            <span className="manifest-title">RIGHT-SIZED KUBERNETES MANIFEST</span>
                            <span className="manifest-badge">[PRODUCTION READY]</span>
                          </div>
                          <div className="manifest-actions">
                            <button
                              type="button"
                              className="btn-manifest-action"
                              onClick={() => handleCopyYaml(activeService.optimization?.optimized_yaml || generateFallbackYaml(activeService))}
                            >
                              {copiedServiceYaml ? '[COPIED]' : '[COPY YAML]'}
                            </button>
                            <button
                              type="button"
                              className="btn-manifest-action btn-manifest-download"
                              onClick={() => handleDownloadYaml(activeService.name, activeService.optimization?.optimized_yaml || generateFallbackYaml(activeService))}
                            >
                              [DOWNLOAD YAML]
                            </button>
                          </div>
                        </div>
                        <div className="manifest-code-wrapper">
                          <pre className="manifest-code-block">
                            <code>{activeService.optimization?.optimized_yaml || generateFallbackYaml(activeService)}</code>
                          </pre>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : activeService.error ? (
                  <div className="error-banner">
                    <strong>Failure Details:</strong>
                    <pre>{activeService.error}</pre>
                  </div>
                ) : (
                  <div className="pending-insights">
                    <span>Resilience evaluation in progress... Telemetry will update dynamically.</span>
                  </div>
                )}

                {/* Iterative Binary Search Convergence Stream */}
                {(activeService.iterations?.length > 0 || activeService.optimization?.iterations?.length > 0) && (
                  <div className="convergence-section">
                    <div className="convergence-header">
                      <div className="convergence-title-group">
                        <span className="indicator-pip" />
                        <h4>BINARY SEARCH OPTIMIZATION STREAM</h4>
                      </div>
                      <span className="convergence-count">
                        {(activeService.iterations || activeService.optimization?.iterations || []).length} TRIALS RECORDED
                      </span>
                    </div>

                    <div className="trial-stream-container">
                      {(activeService.iterations || activeService.optimization?.iterations || []).map((iter) => {
                        const isPass = iter.sla_passed ?? iter.passed
                        const diffVal = iter.difference !== undefined ? iter.difference : (iter.new_bounds ? Math.abs(parseInt(iter.new_bounds[1]) - parseInt(iter.new_bounds[0])) : null)
                        const vector = iter.chaos_vector || {}
                        const culprit = iter.culprit || (!isPass && iter.parameter && iter.parameter !== 'Compound' ? iter.parameter : null)
                        const paramStates = iter.parameters_state || null
                        const recConfig = iter.recommended_config || {
                          memory_limit: activeService.metrics?.memory_max ? `${Math.max(32, Math.round((activeService.metrics.memory_max / (1024 * 1024)) * 1.25))}Mi` : '40Mi',
                          memory_request: activeService.metrics?.memory_max ? `${Math.max(16, Math.round((activeService.metrics.memory_max / (1024 * 1024)) * 0.8))}Mi` : '26Mi',
                          cpu_limit: activeService.metrics?.cpu_max ? `${Math.max(50, Math.round(activeService.metrics.cpu_max * 1000 * 1.25))}m` : '62m',
                          cpu_request: activeService.metrics?.cpu_max ? `${Math.max(25, Math.round(activeService.metrics.cpu_max * 1000 * 0.8))}m` : '40m',
                        }

                        return (
                          <div key={iter.iteration} className={`trial-card ${isPass ? 'trial-pass' : 'trial-fail'}`}>
                            {/* Card Top: Header & Verdict */}
                            <div className="trial-card-top">
                              <div className="trial-meta-left">
                                <span className="trial-index-tag">TRIAL {String(iter.iteration).padStart(2, '0')}</span>
                                <span className={`trial-status-badge ${isPass ? 'status-pass' : 'status-fail'}`}>
                                  {isPass ? '[PASS]' : `[BREACH: ${culprit || 'SLA'}]`}
                                </span>
                                {iter.reason && <span className="trial-reason-text">{iter.reason}</span>}
                              </div>
                              <div className="trial-meta-right">
                                <span className={`delta-tag ${diffVal !== null && diffVal <= 16 ? 'delta-converged' : ''}`}>
                                  DELTA: {diffVal !== null ? `${diffVal}M` : 'N/A'} {diffVal !== null && diffVal <= 16 ? '(CONVERGED)' : ''}
                                </span>
                              </div>
                            </div>

                            {/* Middle: 5-Chaos Vector Bar */}
                            <div className="trial-vector-row">
                              <span className="vector-label">APPLIED 5-CHAOS:</span>
                              <div className="vector-chips-group">
                                <span className={`vector-chip ${culprit === 'RAM' ? 'chip-culprit' : isPass ? 'chip-pass' : ''}`}>
                                  <span className="chip-key">RAM</span>
                                  <code className="chip-val">{vector.memory || (iter.vector?.RAM ? `${iter.vector.RAM}M` : iter.tested_value || iter.display)}</code>
                                </span>
                                <span className={`vector-chip ${culprit === 'CPU' ? 'chip-culprit' : isPass ? 'chip-pass' : ''}`}>
                                  <span className="chip-key">CPU</span>
                                  <code className="chip-val">{vector.cpu || (iter.vector?.CPU ? `${iter.vector.CPU}%` : '60%')}</code>
                                </span>
                                <span className={`vector-chip ${culprit === 'DELAY' ? 'chip-culprit' : isPass ? 'chip-pass' : ''}`}>
                                  <span className="chip-key">DELAY</span>
                                  <code className="chip-val">{vector.delay || (iter.vector?.DELAY ? `${iter.vector.DELAY}ms` : '100ms')}</code>
                                </span>
                                <span className={`vector-chip ${culprit === 'LOSS' ? 'chip-culprit' : isPass ? 'chip-pass' : ''}`}>
                                  <span className="chip-key">LOSS</span>
                                  <code className="chip-val">{vector.loss || (iter.vector?.LOSS ? `${iter.vector.LOSS}%` : '3%')}</code>
                                </span>
                                <span className="vector-chip">
                                  <span className="chip-key">PARTITION</span>
                                  <code className="chip-val">{vector.partition || activeService.name}</code>
                                </span>
                              </div>
                            </div>

                            {/* Iteration Recommended Sizing Configuration Row */}
                            <div className="trial-rec-config-row">
                              <span className="rec-config-label">RECOMMENDED CONFIG:</span>
                              <div className="rec-config-chips-group">
                                <span className="rec-config-chip">
                                  <span className="rec-chip-key">MEM LIMIT:</span>
                                  <code className="rec-chip-val highlight-val">{recConfig.memory_limit}</code>
                                </span>
                                <span className="rec-config-chip">
                                  <span className="rec-chip-key">MEM REQ:</span>
                                  <code className="rec-chip-val highlight-secondary">{recConfig.memory_request}</code>
                                </span>
                                <span className="rec-config-chip">
                                  <span className="rec-chip-key">CPU LIMIT:</span>
                                  <code className="rec-chip-val highlight-val">{recConfig.cpu_limit}</code>
                                </span>
                                <span className="rec-config-chip">
                                  <span className="rec-chip-key">CPU REQ:</span>
                                  <code className="rec-chip-val highlight-secondary">{recConfig.cpu_request}</code>
                                </span>
                              </div>
                            </div>

                            {/* Parameter Bounds State Row (if available) */}
                            {paramStates && (
                              <div className="trial-param-bounds-row">
                                <span className="bounds-row-label">BOUNDS:</span>
                                <span className={`param-bound-chip ${culprit === 'RAM' ? 'is-culprit' : ''}`}>
                                  RAM: <code>[{paramStates.RAM.low}M, {paramStates.RAM.high}M]</code>
                                </span>
                                <span className={`param-bound-chip ${culprit === 'CPU' ? 'is-culprit' : ''}`}>
                                  CPU: <code>[{paramStates.CPU.low}%, {paramStates.CPU.high}%]</code>
                                </span>
                                <span className={`param-bound-chip ${culprit === 'DELAY' ? 'is-culprit' : ''}`}>
                                  DELAY: <code>[{paramStates.DELAY.low}ms, {paramStates.DELAY.high}ms]</code>
                                </span>
                                <span className={`param-bound-chip ${culprit === 'LOSS' ? 'is-culprit' : ''}`}>
                                  LOSS: <code>[{paramStates.LOSS.low}%, {paramStates.LOSS.high}%]</code>
                                </span>
                              </div>
                            )}

                            {/* Bottom: Decision Step & Bounds */}
                            <div className="trial-card-bottom">
                              <div className="step-decision-text">
                                <span className="step-prefix">&gt;</span>
                                <span className="step-detail">{iter.step_taken}</span>
                              </div>
                              <div className="midpoint-next-tag">
                                {iter.next_midpoint && !iter.converged ? (
                                  <span>NEXT MIDPOINT: <code>{iter.next_midpoint}</code></span>
                                ) : (
                                  <span className="converged-final-tag">CONVERGED AT {activeService.optimization?.max_safe_tolerance || iter.tested_value}</span>
                                )}
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Terminal Window with Log Partitioning */}
              <div className="terminal-container">
                <div className="terminal-tabs-bar">
                  <div className="tab-buttons">
                    <button
                      type="button"
                      className={`tab-btn ${activeLogTab === 'service' ? 'active' : ''}`}
                      onClick={() => setActiveLogTab('service')}
                    >
                      {activeService.name} Logs ({serviceLogs[activeService.name]?.length || 0})
                    </button>
                    <button
                      type="button"
                      className={`tab-btn ${activeLogTab === 'all' ? 'active' : ''}`}
                      onClick={() => setActiveLogTab('all')}
                    >
                      Global Console ({globalLogs.length})
                    </button>
                  </div>

                  <div className="terminal-tools">
                    <button
                      type="button"
                      className={`autoscroll-toggle-btn ${autoScroll ? 'active' : ''}`}
                      onClick={() => setAutoScroll(!autoScroll)}
                      title="Toggle auto-scroll to bottom"
                    >
                      {autoScroll ? 'Auto-scroll: ON' : 'Auto-scroll: OFF'}
                    </button>
                    <input
                      type="text"
                      className="log-search-input"
                      placeholder="Filter logs..."
                      value={logFilterQuery}
                      onChange={(e) => setLogFilterQuery(e.target.value)}
                    />
                  </div>
                </div>

                <div className="terminal-window">
                  <div className="terminal-bar">
                    <span />
                    <span />
                    <span />
                    <strong>
                      {activeLogTab === 'service' ? activeService.name : 'all-workloads'} :: stream
                    </strong>
                  </div>

                  <div className="terminal-content">
                    {displayedLogs.length === 0 ? (
                      <div className="empty-terminal-text">
                        No log entries found for this view.
                      </div>
                    ) : (
                      displayedLogs.map((entry, idx) => (
                        <div key={idx} className={`log-line log-${entry.type}`}>
                          <span className="log-symbol">
                            {entry.type === 'command'
                              ? '$'
                              : entry.type === 'success'
                              ? '[OK]'
                              : entry.type === 'error'
                              ? '!'
                              : '>'}
                          </span>
                          <span className="log-text">{entry.text}</span>
                        </div>
                      ))
                    )}
                    {running && (
                      <div className="log-line log-cursor">
                        <span className="log-symbol">&gt;</span>
                        <span className="typing">
                          streaming backend output<span>_</span>
                        </span>
                      </div>
                    )}
                    <div ref={terminalBottomRef} />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">
              <p>Select a microservice on the left to inspect its logs and resilience SLA verdict.</p>
            </div>
          )}
        </section>
      </div>

      {/* Footer */}
      <footer>
        <span>AI K8s Twin</span>
        <span>Microservice Resilience &amp; Right-Sizing Control Plane</span>
        <span>v0.2 / Local Minikube</span>
      </footer>
    </main>
  )
}

export default App
