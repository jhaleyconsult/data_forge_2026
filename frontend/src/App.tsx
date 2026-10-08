import { useState } from "react"
import {
  Activity,
  ArrowRight,
  BedDouble,
  Bell,
  CheckCircle2,
  Clock3,
  DoorOpen,
  Hospital,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  UserRound,
  Users,
  X,
  type LucideIcon,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import "./prototype.css"

type RoomState =
  | "available"
  | "occupied"
  | "discharge_pending"
  | "needs_cleaning"
  | "cleaning"

type Role = "nurse" | "evs"
type Recipient = "Nurse" | "EVS"

interface Room {
  id: string
  unit: string
  state: RoomState
  updatedAt: number
}

interface ActivityEvent {
  id: string
  roomId: string
  actor: Recipient
  recipient?: Recipient
  message: string
  at: number
}

interface RoomAction {
  label: string
  next: RoomState
  message: string
  icon: LucideIcon
  notifyTo?: Recipient
  primary?: boolean
}

const initialRooms: Room[] = [
  { id: "4W-412", unit: "4 West · Med-Surg", state: "occupied", updatedAt: Date.now() - 18 * 60_000 },
  { id: "4W-415", unit: "4 West · Med-Surg", state: "discharge_pending", updatedAt: Date.now() - 7 * 60_000 },
  { id: "4W-418", unit: "4 West · Med-Surg", state: "needs_cleaning", updatedAt: Date.now() - 12 * 60_000 },
  { id: "4W-421", unit: "4 West · Med-Surg", state: "needs_cleaning", updatedAt: Date.now() - 4 * 60_000 },
  { id: "3S-206", unit: "3 South · Med-Surg", state: "cleaning", updatedAt: Date.now() - 9 * 60_000 },
  { id: "3S-208", unit: "3 South · Med-Surg", state: "available", updatedAt: Date.now() - 16 * 60_000 },
  { id: "ICU-08", unit: "Intensive Care", state: "occupied", updatedAt: Date.now() - 25 * 60_000 },
  { id: "ICU-11", unit: "Intensive Care", state: "available", updatedAt: Date.now() - 3 * 60_000 },
]

const stateOrder: RoomState[] = [
  "available",
  "occupied",
  "discharge_pending",
  "needs_cleaning",
  "cleaning",
]

const stateDetails: Record<RoomState, { label: string; description: string }> = {
  available: { label: "Available", description: "Ready for the next patient" },
  occupied: { label: "Occupied", description: "Patient currently in room" },
  discharge_pending: {
    label: "Discharge pending",
    description: "EVS alerted · awaiting departure",
  },
  needs_cleaning: {
    label: "Needs cleaning",
    description: "In the EVS queue",
  },
  cleaning: { label: "Cleaning", description: "EVS is in the room" },
}

const allowedTransitions: Record<RoomState, RoomState[]> = {
  available: ["occupied"],
  occupied: ["discharge_pending"],
  discharge_pending: ["needs_cleaning"],
  needs_cleaning: ["cleaning"],
  cleaning: ["available"],
}

const timestamp = () => Date.now()

function makeInitialEvents(): ActivityEvent[] {
  const now = timestamp()
  return [
    {
      id: "sample-1",
      roomId: "4W-415",
      actor: "Nurse",
      recipient: "EVS",
      message: "Marked ready to leave. EVS was notified.",
      at: now - 7 * 60_000,
    },
    {
      id: "sample-2",
      roomId: "4W-418",
      actor: "Nurse",
      recipient: "EVS",
      message: "Patient departure confirmed. Added to the cleaning queue.",
      at: now - 12 * 60_000,
    },
    {
      id: "sample-3",
      roomId: "3S-206",
      actor: "EVS",
      message: "Cleaner started the room turnover.",
      at: now - 9 * 60_000,
    },
  ]
}

function getAction(room: Room, role: Role): RoomAction | null {
  if (role === "nurse") {
    if (room.state === "available") {
      return {
        label: "Mark occupied",
        next: "occupied",
        message: "Room marked occupied for an incoming patient.",
        icon: BedDouble,
      }
    }
    if (room.state === "occupied") {
      return {
        label: "Patient ready to leave",
        next: "discharge_pending",
        message: "Patient is discharge-ready. EVS was notified.",
        icon: DoorOpen,
        notifyTo: "EVS",
        primary: true,
      }
    }
    if (room.state === "discharge_pending") {
      return {
        label: "Confirm patient left",
        next: "needs_cleaning",
        message: "Patient departure confirmed. Room entered the EVS queue.",
        icon: CheckCircle2,
        notifyTo: "EVS",
        primary: true,
      }
    }
    return null
  }

  if (room.state === "needs_cleaning") {
    return {
      label: "Start cleaning",
      next: "cleaning",
      message: "Cleaner started room turnover.",
      icon: Sparkles,
      primary: true,
    }
  }
  if (room.state === "cleaning") {
    return {
      label: "Mark room clean",
      next: "available",
      message: "Cleaning complete. Nurse was notified the room is available.",
      icon: CheckCircle2,
      notifyTo: "Nurse",
      primary: true,
    }
  }
  return null
}

function getWaitingMessage(room: Room, role: Role): string {
  if (role === "nurse" && room.state === "needs_cleaning") {
    return "EVS notified · waiting for cleaner"
  }
  if (role === "nurse" && room.state === "cleaning") {
    return "Cleaner is working · nurse will be notified"
  }
  if (role === "evs" && room.state === "discharge_pending") {
    return "Awaiting patient departure"
  }
  return stateDetails[room.state].description
}

function App() {
  const [rooms, setRooms] = useState<Room[]>(initialRooms)
  const [events, setEvents] = useState<ActivityEvent[]>(makeInitialEvents)
  const [role, setRole] = useState<Role>("nurse")
  const [query, setQuery] = useState("")
  const [notice, setNotice] = useState<string | null>(null)

  const counts = stateOrder.reduce(
    (result, state) => ({
      ...result,
      [state]: rooms.filter((room) => room.state === state).length,
    }),
    {} as Record<RoomState, number>,
  )
  const waitingForEvs = counts.discharge_pending + counts.needs_cleaning
  const notificationCount = events.filter(
    (event) => event.recipient === (role === "nurse" ? "Nurse" : "EVS"),
  ).length

  const visibleRooms = rooms.filter((room) => {
    const visibleToRole =
      role === "nurse"
        ? true
        : room.state === "discharge_pending" ||
          room.state === "needs_cleaning" ||
          room.state === "cleaning"
    const search = `${room.id} ${room.unit}`.toLowerCase()
    return visibleToRole && search.includes(query.trim().toLowerCase())
  })

  function transitionRoom(room: Room, action: RoomAction) {
    if (!allowedTransitions[room.state].includes(action.next)) return

    const at = timestamp()
    setRooms((current) =>
      current.map((item) =>
        item.id === room.id ? { ...item, state: action.next, updatedAt: at } : item,
      ),
    )
    const event: ActivityEvent = {
      id: `${at}-${room.id}`,
      roomId: room.id,
      actor: role === "nurse" ? "Nurse" : "EVS",
      recipient: action.notifyTo,
      message: action.message,
      at,
    }
    setEvents((current) => [event, ...current].slice(0, 12))
    setNotice(
      action.notifyTo
        ? `${action.notifyTo} notified · ${room.id}`
        : `Room updated · ${room.id}`,
    )
  }

  function resetDemo() {
    setRooms(initialRooms.map((room) => ({ ...room, updatedAt: timestamp() })))
    setEvents(makeInitialEvents())
    setRole("nurse")
    setQuery("")
    setNotice("Demo room states reset")
  }

  const statItems: {
    state: RoomState
    icon: LucideIcon
    detail: string
  }[] = [
    { state: "occupied", icon: Users, detail: "Patient in room" },
    { state: "discharge_pending", icon: Clock3, detail: "EVS alerted" },
    { state: "needs_cleaning", icon: Sparkles, detail: "Cleaner needed" },
    { state: "cleaning", icon: Activity, detail: "In progress" },
    { state: "available", icon: CheckCircle2, detail: "Ready for use" },
  ]

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <Hospital size={20} strokeWidth={1.8} />
          </div>
          <div className="brand-copy">
            <span className="brand-name">TURNOVER</span>
            <span className="brand-section">ROOM OPERATIONS</span>
          </div>
        </div>

        <div className="topbar-right">
          <div className="prototype-indicator">
            <span className="prototype-dot" />
            <span>LOCAL PROTOTYPE</span>
          </div>
          <Separator orientation="vertical" className="topbar-separator" />
          <div className="current-role">
            <div className="role-avatar">
              {role === "nurse" ? <Stethoscope size={16} /> : <Sparkles size={16} />}
            </div>
            <span>{role === "nurse" ? "Nursing view" : "EVS view"}</span>
          </div>
          <Button
            variant="outline"
            size="icon"
            className="notification-button"
            aria-label={`${notificationCount} notifications for ${role === "nurse" ? "nurse" : "EVS"}`}
          >
            <Bell size={17} />
            {notificationCount > 0 && <span className="notification-count">{notificationCount}</span>}
          </Button>
        </div>
      </header>

      <main className="dashboard-page">
        <section className="page-heading">
          <div>
            <div className="eyebrow"><span>OPERATIONS</span><span className="eyebrow-slash">/</span><span>BED TURNOVER</span></div>
            <h1>Room turnover</h1>
            <p className="page-subtitle">
              A shared handoff from discharge readiness to a clean room, ready for the next patient.
            </p>
          </div>
          <Badge variant="outline" className="sample-badge">
            <ShieldCheck size={13} /> SAMPLE DATA · NO LIVE EHR
          </Badge>
        </section>

        <section className="state-summary" aria-label="Room state summary">
          {statItems.map(({ state, icon: Icon, detail }) => (
            <div className={`summary-tile summary-${state}`} key={state}>
              <div className="summary-topline">
                <span>{stateDetails[state].label}</span>
                <Icon size={16} strokeWidth={1.8} />
              </div>
              <div className="summary-value">{counts[state]}</div>
              <div className="summary-detail">{detail}</div>
            </div>
          ))}
        </section>

        <section className="workspace-section">
          <div className="workspace-heading">
            <div className="workspace-title">
              <div className="eyebrow">SHARED ROOM BOARD</div>
              <h2>{role === "nurse" ? "Nursing handoff" : "EVS cleaning queue"}</h2>
              <p>
                {role === "nurse"
                  ? "Update a room when the patient is ready to leave, then confirm departure."
                  : "Work the cleaning queue and return finished rooms to nursing."}
              </p>
            </div>
            <Tabs
              value={role}
              onValueChange={(value) => {
                if (value === "nurse" || value === "evs") setRole(value)
              }}
              className="role-switch"
            >
              <TabsList className="role-switch-list">
                <TabsTrigger value="nurse" className="role-switch-tab">
                  <Stethoscope size={15} /> Nurse
                </TabsTrigger>
                <TabsTrigger value="evs" className="role-switch-tab">
                  <Sparkles size={15} /> EVS
                  {waitingForEvs > 0 && <span className="tab-count">{waitingForEvs}</span>}
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          <div className="content-grid">
            <Card className="room-board-card">
              <CardHeader className="room-board-header">
                <div>
                  <CardTitle>{role === "nurse" ? "Rooms on unit" : "Active EVS queue"}</CardTitle>
                  <p className="section-caption">
                    {role === "nurse"
                      ? `${visibleRooms.length} sample rooms · select an action to record a handoff`
                      : `${visibleRooms.length} rooms awaiting or receiving cleaning`}
                  </p>
                </div>
                <Button variant="ghost" size="sm" className="reset-button" onClick={resetDemo}>
                  <RotateCcw size={14} /> Reset demo
                </Button>
              </CardHeader>
              <CardContent className="room-board-content">
                <label className="room-search">
                  <Search size={16} aria-hidden="true" />
                  <input
                    type="search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search by room or unit"
                    aria-label="Search by room or unit"
                  />
                  <span className="search-hint">⌘ K</span>
                </label>

                <div className="room-list" aria-live="polite">
                  {visibleRooms.length > 0 ? (
                    visibleRooms.map((room) => {
                      const action = getAction(room, role)
                      const ActionIcon = action?.icon
                      return (
                        <article className={`room-row room-row-${room.state}`} key={room.id}>
                          <div className="room-location">
                            <div className="room-glyph"><BedDouble size={17} /></div>
                            <div>
                              <div className="room-id">{room.id}</div>
                              <div className="room-unit">{room.unit}</div>
                            </div>
                          </div>

                          <div className="room-state-block">
                            <Badge variant="outline" className={`state-badge state-${room.state}`}>
                              <span className="state-dot" />
                              {stateDetails[room.state].label}
                            </Badge>
                            <span className="room-state-detail">
                              {getWaitingMessage(room, role)}
                            </span>
                          </div>

                          <div className="room-updated">
                            <span className="updated-label">UPDATED</span>
                            <span>{formatTime(room.updatedAt)}</span>
                          </div>

                          <div className="room-action">
                            {action && ActionIcon ? (
                              <Button
                                size="sm"
                                variant={action.primary ? "default" : "outline"}
                                className="room-action-button"
                                onClick={() => transitionRoom(room, action)}
                              >
                                <ActionIcon size={15} />
                                <span>{action.label}</span>
                                <ArrowRight size={14} className="action-arrow" />
                              </Button>
                            ) : (
                              <span className="no-action">{role === "evs" ? "No action" : "In progress"}</span>
                            )}
                          </div>
                        </article>
                      )
                    })
                  ) : (
                    <div className="empty-rooms">
                      <Search size={20} />
                      <strong>No rooms match</strong>
                      <span>Try a different room number or unit.</span>
                    </div>
                  )}
                </div>

                <div className="board-footnote">
                  <span className="footnote-mark"><ShieldCheck size={14} /></span>
                  <span>Fictional room states for workflow demonstration. No patient identifiers are used.</span>
                </div>
              </CardContent>
            </Card>

            <aside className="side-column">
              <Card className="activity-card">
                <CardHeader className="activity-header">
                  <div className="activity-title-wrap">
                    <div className="activity-icon"><Activity size={17} /></div>
                    <div>
                      <CardTitle>Handoff activity</CardTitle>
                      <p className="section-caption">Room events and routed notifications</p>
                    </div>
                  </div>
                  <Badge variant="secondary" className="activity-live-badge">
                    <span className="activity-live-dot" /> LOCAL
                  </Badge>
                </CardHeader>
                <CardContent className="activity-content">
                  {events.length > 0 ? (
                    <ol className="event-list">
                      {events.slice(0, 6).map((event, index) => (
                        <li className="event-item" key={event.id}>
                          <div className={`event-rail ${index === events.length - 1 ? "event-rail-last" : ""}`}>
                            <span className={`event-avatar event-${event.actor.toLowerCase()}`}>
                              {event.actor === "Nurse" ? <Stethoscope size={14} /> : <Sparkles size={14} />}
                            </span>
                          </div>
                          <div className="event-copy">
                            <div className="event-heading">
                              <strong>{event.roomId}</strong>
                              <time>{formatTime(event.at)}</time>
                            </div>
                            <p>{event.message}</p>
                            <span className={`event-route ${event.recipient ? "event-routed" : ""}`}>
                              {event.recipient ? <Bell size={11} /> : <UserRound size={11} />}
                              {event.recipient ? `Sent to ${event.recipient}` : `Recorded by ${event.actor}`}
                            </span>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <div className="empty-events">Room actions will appear here.</div>
                  )}
                </CardContent>
                <Separator />
                <div className="activity-footer">
                  <span className="activity-footer-icon"><ShieldCheck size={14} /></span>
                  <span>Notifications are simulated in this browser session.</span>
                </div>
              </Card>

              <Card className="workflow-card">
                <CardHeader className="workflow-header">
                  <div className="eyebrow">ROOM STATE MACHINE</div>
                  <CardTitle>One shared sequence</CardTitle>
                </CardHeader>
                <CardContent className="workflow-content">
                  {stateOrder.map((state, index) => (
                    <div className="workflow-step" key={state}>
                      <span className={`workflow-node workflow-${state}`}>
                        {index + 1}
                      </span>
                      <span className="workflow-label">{stateDetails[state].label}</span>
                      {index < stateOrder.length - 1 && <ArrowRight size={13} className="workflow-arrow" />}
                    </div>
                  ))}
                </CardContent>
              </Card>
            </aside>
          </div>
        </section>

        <footer className="page-footer">
          <span><Hospital size={14} /> Bed turnover workflow prototype</span>
          <span>Local-only demo · No live clinical system connection</span>
        </footer>
      </main>

      {notice && (
        <div className="toast-notice" role="status" aria-live="polite">
          <span className="toast-check"><CheckCircle2 size={17} /></span>
          <span>{notice}</span>
          <button type="button" aria-label="Dismiss notification" onClick={() => setNotice(null)}>
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  )
}

function formatTime(value: number): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(value)
}

export default App