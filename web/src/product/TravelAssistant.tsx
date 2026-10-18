import { PlaceCover } from '../components/PlacePhotos';
import { approvedPhotos } from '../data/placeContentRepository';
import {
  ArrowUp,
  ArrowUpRight,
  Compass,
  MapPin,
  MessageCircle,
  Sparkles,
  X,
} from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Link, useLocation } from "react-router-dom";
import {
  CompanionThinking,
  companionAnswer,
} from "../components/CompanionThinking";
import { ApiTripPlanningRepository } from "../data/apiTripPlanningRepository";
import { createExploreRepository } from "../data/exploreRepository";
import { readAssistantStream } from "../data/assistantStream";
import {
  assistantTopic,
  productAssistantContext,
  type AssistantProductReadContext,
} from "../data/productAssistantContext";
import type { ExplorePlace, ExploreRepository } from "../domain/explore";
import type { AssistantSession, TripPlanningRepository } from "../domain/types";
import "./TravelAssistant.css";

interface RouteReadRequest {
  origin_place_id: string;
  destination_place_id: string;
  mode: "walk" | "driving";
}

export interface TravelAssistantContext extends AssistantProductReadContext {
  prompt?: string;
  returnTo?: string;
}

type SessionRepository = Pick<TripPlanningRepository, "getAssistantSession">;
interface AssistantState {
  returnTo: string;
  openAssistant: (context?: TravelAssistantContext) => void;
  closeAssistant: () => void;
  context: TravelAssistantContext;
  resetContext: () => void;
  session?: AssistantSession;
  draft: string;
  setDraft: (value: string) => void;
  busy: boolean;
  loading: boolean;
  error: string;
  submission: string;
  stream: string;
  status: string;
  send: (
    routeRequest?: RouteReadRequest,
    routeMessage?: string,
  ) => Promise<void>;
  retrySession: () => void;
  exploreRepository: ExploreRepository;
}
const AssistantContext = createContext<AssistantState | null>(null);
const defaultTripRepository = new ApiTripPlanningRepository();
const defaultExploreRepository = createExploreRepository();

function topicMessages(session?: AssistantSession) {
  const messages = session?.messages ?? [];
  return import.meta.env.VITE_ASSISTANT_CONTEXT_CONTRACT ===
    "assistant-context-v1"
    ? messages.filter(
        (message) => message.context?.topic_id === assistantTopic(),
      )
    : messages;
}

export function useTravelAssistant() {
  const value = useContext(AssistantContext);
  if (!value) throw new Error("TravelAssistantProvider is required");
  return value;
}

export function TravelAssistantProvider({
  children,
  tripRepository = defaultTripRepository,
  exploreRepository = defaultExploreRepository,
}: {
  children: ReactNode;
  tripRepository?: SessionRepository;
  exploreRepository?: ExploreRepository;
}) {
  const location = useLocation();
  const [opened, setOpened] = useState(false);
  const [context, setContext] = useState<TravelAssistantContext>(() => {
    try {
      return JSON.parse(
        sessionStorage.getItem("roamsync.assistant.context") || "{}",
      );
    } catch {
      return {};
    }
  });
  const [returnTo, setReturnTo] = useState(
    () => sessionStorage.getItem("roamsync.assistant.return") || "/",
  );
  useEffect(() => {
    try {
      sessionStorage.setItem(
        "roamsync.assistant.context",
        JSON.stringify(context),
      );
      sessionStorage.setItem("roamsync.assistant.return", returnTo);
    } catch {
      /* Optional browser recovery. */
    }
  }, [context, returnTo]);
  const [sessions, setSessions] = useState<Record<string, AssistantSession>>(
    {},
  );
  const [draft, setDraft] = useState(
    () => sessionStorage.getItem("roamsync.assistant.draft") || "",
  );
  useEffect(() => {
    try {
      sessionStorage.setItem("roamsync.assistant.draft", draft);
    } catch {
      /* Keep conversation in memory. */
    }
  }, [draft]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [submission, setSubmission] = useState("");
  const [stream, setStream] = useState("");
  const [status, setStatus] = useState("");
  const [retry, setRetry] = useState(0);
  const retryMessage = useRef<{
    scope: string;
    message: string;
    id: string;
  } | null>(null);
  const sending = useRef(false);
  const sendingScope = useRef<string | null>(null);
  const unified = import.meta.env.VITE_DISCOVERY_PRODUCT === "true";
  const sessionTripId = unified ? undefined : context.tripId;
  const scope = sessionTripId ?? "global";
  const session = sessions[scope];
  const active = opened || location.pathname === "/assistant";
  useEffect(() => {
    setOpened(false);
  }, [location.pathname]);

  const openAssistant = useCallback(
    (next?: TravelAssistantContext) => {
      if (next) {
        // Place entry always starts from global scope unless a Trip was explicitly supplied.
        const { prompt: _prompt, returnTo: _returnTo, ...readContext } = next;
        setContext(readContext);
        if (
          next.prompt !== undefined ||
          next.place?.id !== context.place?.id ||
          next.tripId !== context.tripId ||
          next.city !== context.city ||
          next.draftContext?.draftId !== context.draftContext?.draftId ||
          JSON.stringify(next.places?.map((p) => p.id)) !==
            JSON.stringify(context.places?.map((p) => p.id))
        )
          setDraft(
            next.prompt ??
              (next.place
                ? `想了解${next.place.name}，有哪些值得留意的地方？`
                : ""),
          );
        setError("");
      }
      if (next?.returnTo) setReturnTo(next.returnTo);
      else if (location.pathname !== "/assistant")
        setReturnTo(location.pathname + location.search);
      setOpened(true);
    },
    [location.pathname, location.search, context],
  );
  const resetContext = () => {
    setContext({});
    setDraft("");
    setError("");
  };
  const closeAssistant = useCallback(() => setOpened(false), []);

  useEffect(() => {
    if (!active || session) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    (async () => {
      if (!tripRepository.getAssistantSession)
        throw new Error("当前服务暂不支持 AI 对话，请继续浏览探索和收藏。");
      const next = await tripRepository.getAssistantSession(sessionTripId);
      if (next.trip_id !== (sessionTripId ?? null))
        throw new Error("会话关联的行程与当前选择不一致，请重试。");
      if (!cancelled) setSessions((values) => ({ ...values, [scope]: next }));
    })()
      .catch((cause) => {
        if (!cancelled) setError(messageOf(cause));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active, sessionTripId, retry, scope, session, tripRepository]);

  const send = async (
    routeRequest?: RouteReadRequest,
    routeMessage?: string,
  ) => {
    const message = routeMessage ?? draft.trim();
    if (!message || !session || busy || loading || sending.current) return;
    sending.current = true;
    sendingScope.current = scope;
    const selectedScope = scope;
    const selectedContext = context;
    const previous = retryMessage.current;
    const id =
      previous?.scope === scope && previous.message === message
        ? previous.id
        : crypto.randomUUID();
    retryMessage.current = { scope, message, id };
    setBusy(true);
    setError("");
    setSubmission(message);
    setStream("");
    setStatus("正在整理旅行建议…");
    setDraft("");
    try {
      const requestContext = productAssistantContext(
        selectedContext,
        import.meta.env.VITE_ASSISTANT_CONTEXT_CONTRACT,
      );
      const response = await fetch(
        `/api/v1/assistant/sessions/${encodeURIComponent(session.id)}/messages/stream`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            message,
            message_id: id,
            ...requestContext,
            ...(routeRequest && "context" in requestContext
              ? {
                  context: {
                    ...requestContext.context,
                    route_request: routeRequest,
                  },
                }
              : {}),
          }),
        },
      );
      const next = await readAssistantStream(response, (event) => {
        if (event.type === "answer_delta")
          setStream((value) => value + event.delta);
        if (event.type === "status") setStatus(event.message);
        if (event.type === "reset") {
          setStream("");
          setStatus("正在重新整理回答…");
        }
      });
      if (next.trip_id !== (sessionTripId ?? null))
        throw new Error("返回的会话关联发生变化，请前往行程页面确认。");
      setSessions((values) => ({ ...values, [selectedScope]: next }));
      retryMessage.current = null;
    } catch (cause) {
      setError(messageOf(cause));
      setDraft((value) => value || message);
    } finally {
      sending.current = false;
      sendingScope.current = null;
      setBusy(false);
      setSubmission("");
      setStream("");
      setStatus("");
    }
  };
  const value: AssistantState = {
    returnTo,
    openAssistant,
    closeAssistant,
    context,
    resetContext,
    session,
    draft,
    setDraft,
    busy,
    loading,
    error,
    submission: sendingScope.current === scope ? submission : "",
    stream,
    status,
    send,
    retrySession: () => setRetry((value) => value + 1),
    exploreRepository,
  };
  return (
    <AssistantContext.Provider value={value}>
      {children}
      {opened && location.pathname !== "/assistant" && (
        <div className="travel-assistant-overlay">
          <button
            className="travel-assistant-scrim"
            aria-label="关闭 AI 旅行助手"
            onClick={() => setOpened(false)}
          />
          <section
            className="travel-assistant-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="AI 旅行助手"
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpened(false);
            }}
          >
            <AssistantConversation drawer />
          </section>
        </div>
      )}
    </AssistantContext.Provider>
  );
}

export function AssistantPage() {
  return (
    <main className="travel-assistant-page">
      <AssistantConversation />
    </main>
  );
}

function AssistantConversation({ drawer = false }: { drawer?: boolean }) {
  const assistant = useTravelAssistant();
  const end = useRef<HTMLDivElement>(null);
  const composing = useRef(false);
  const { context, session, loading, busy, error, draft, closeAssistant } =
    assistant;
  const messages = topicMessages(session);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [session?.messages.length, assistant.stream, assistant.submission]);
  useEffect(() => {
    if (!drawer) return;
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialog = document.querySelector<HTMLElement>(
      ".travel-assistant-drawer",
    );
    dialog?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeAssistant();
      if (event.key !== "Tab" || !dialog) return;
      const targets = Array.from(
        dialog.querySelectorAll<HTMLElement>(
          "a[href],button:not(:disabled),input:not(:disabled),textarea:not(:disabled),summary",
        ),
      );
      const first = targets[0];
      const last = targets.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, [drawer, closeAssistant]);
  return (
    <div className="travel-assistant-conversation">
      <header className="travel-assistant-header">
        <span className="travel-assistant-symbol">
          <Sparkles size={22} />
        </span>
        <div>
          <strong>AI 旅行助手</strong>
          <span>聊灵感，找去处，把旅行慢慢想清楚</span>
        </div>
        {drawer && (
          <>
            <Link
              className="travel-assistant-icon"
              to="/assistant"
              aria-label="展开完整对话"
            >
              <ArrowUpRight size={20} />
            </Link>
            <button
              className="travel-assistant-icon"
              onClick={assistant.closeAssistant}
              aria-label="关闭助手"
            >
              <X size={20} />
            </button>
          </>
        )}
      </header>
      <div className="travel-assistant-context">
        {context.place ? (
          <>
            <MapPin size={15} />
            <span>
              正在讨论：
              <Link
                state={{ from: "/assistant" }}
                to={`/places/${encodeURIComponent(context.place.id)}`}
              >
                {context.place.name}
              </Link>{" "}
              · {context.place.city}
            </span>
          </>
        ) : (
          <>
            <Compass size={15} />
            <span>一起探索下一段旅程</span>
          </>
        )}
        {(context.place ||
          context.tripId ||
          context.places?.length ||
          context.draftContext ||
          context.discovery) && (
          <button onClick={assistant.resetContext} disabled={busy}>
            回到自由聊
          </button>
        )}
      </div>
      {context.place && (
        <div className="travel-assistant-address">
          {context.place.address} · 浏览的地点
        </div>
      )}
      {context.places?.length ? (
        <div className="travel-assistant-context">
          <MapPin size={15} />
          <span>
            正在比较 {context.places.length} 个地点：
            {context.places.map((p) => p.name).join("、")}
          </span>
        </div>
      ) : null}
      {context.discovery && (
        <div className="travel-assistant-address">
          所选区域 · {context.discovery.radius_meters / 1000} 公里内 ·
          比较已知信息，缺失信息保持未知
        </div>
      )}
      {context.draftContext && (
        <div className="travel-assistant-trip">
          正在讨论已保存草稿{" "}
          <Link to={`/drafts/${context.draftContext.draftId}`}>
            返回继续筹划 <ArrowUpRight size={13} />
          </Link>
          <small>未保存编辑请先保存；聊天不会采用方案。</small>
        </div>
      )}
      {context.tripId && (
        <div className="travel-assistant-trip">
          已关联行程{" "}
          <Link to={`/trips/${encodeURIComponent(context.tripId)}`}>
            查看已确认安排 <ArrowUpRight size={13} />
          </Link>
        </div>
      )}
      <div
        className="travel-assistant-messages"
        aria-live="polite"
        aria-busy={busy || loading}
      >
        {!messages.length && !assistant.submission && (
          <div className="travel-assistant-welcome">
            <span className="travel-assistant-welcome-icon">
              <MessageCircle size={29} />
            </span>
            <h1>
              {context.place
                ? `关于${context.place.name}，想聊些什么？`
                : "下一站，想去哪里？"}
            </h1>
            <p>找一座合心意的城市，比较两个目的地，或聊聊当地的吃喝与体验。</p>
            <div className="travel-assistant-prompts">
              {(context.place
                ? ["这个地方适合怎样的旅行者？", "游览前需要了解什么？"]
                : [
                    "想找个适合慢慢逛的城市",
                    "周末想短途旅行，怎么选目的地？",
                    "帮我比较两座城市",
                  ]
              ).map((prompt) => (
                <button
                  key={prompt}
                  disabled={busy}
                  onClick={() => assistant.setDraft(prompt)}
                >
                  {prompt}
                  <ArrowUpRight size={14} />
                </button>
              ))}
            </div>
          </div>
        )}
        {loading && (
          <p className="travel-assistant-status" role="status">
            正在读取对话…
          </p>
        )}
        {messages.map((message) => (
          <div className="travel-assistant-turn" key={message.id}>
            <div className="travel-assistant-user">{message.user}</div>
            <div className="travel-assistant-reply">
              <Sparkles size={17} />
              <div>
                <div className="travel-assistant-text">
                  {companionAnswer(
                    message.companion_result?.response_text ||
                      message.assistant,
                  )}
                </div>
                {!!message.place_cards?.length && (
                  <div className="travel-assistant-suggestions">
                    {message.place_cards
                      .filter((card) =>
                        /^[0-9a-f-]{36}$/i.test(card.place.place_id),
                      )
                      .map((card) => (
                        <span key={card.place.place_id}>
                          <PlaceCover photos={approvedPhotos(card.place.images ?? [], card.place.place_id)} />
                          <Link
                            state={{ from: "/assistant" }}
                            to={`/places/${encodeURIComponent(card.place.place_id)}`}
                          >
                            <MapPin size={13} />
                            {card.place.name} · {card.place.city}
                            <ArrowUpRight size={13} />
                          </Link>
                          {context.place &&
                            card.place.place_id !== context.place.id &&
                            import.meta.env.VITE_ASSISTANT_CONTEXT_CONTRACT ===
                              "assistant-context-v1" && (
                              <button
                                disabled={busy}
                                onClick={() =>
                                  void assistant.send(
                                    {
                                      origin_place_id: context.place!.id,
                                      destination_place_id: card.place.place_id,
                                      mode: "walk",
                                    },
                                    `查询从${context.place!.name}到${card.place.name}的步行路线`,
                                  )
                                }
                              >
                                从讨论地点步行去这里
                              </button>
                            )}
                        </span>
                      ))}
                  </div>
                )}
                {message.read_tools?.comparison && (
                  <div className="travel-assistant-comparison" aria-label="已核实的地点比较">
                    <strong>本次选中地点的已知信息</strong>
                    <p>高德参考信息，非实时报价。缺失字段保持未知。</p>
                    {message.read_tools.comparison.items.map((item) => (
                      <article key={item.place_id}>
                        <Link state={{ from: "/assistant" }} to={`/places/${item.place_id}`}>
                          {item.name} · {item.city}
                        </Link>
                        <p>
                          {item.rating == null ? "暂无评分" : `参考评分 ${item.rating}/5`} · {" "}
                          {item.reference_cost_yuan == null
                            ? "暂无参考消费"
                            : `参考消费约 ¥${item.reference_cost_yuan}/人`}
                        </p>
                        <small>{item.address || "地址暂无"}</small>
                      </article>
                    ))}
                    {message.read_tools.comparison.missing_count > 0 && (
                      <p>有{message.read_tools.comparison.missing_count}个所选地点暂时无法核实，没有以其他地点替代。</p>
                    )}
                  </div>
                )}
                {message.read_tools?.route && (
                  <div className="travel-assistant-route" role="status">
                    {message.read_tools.route.status === "available" &&
                    message.read_tools.route.result ? (
                      <>
                        <strong>
                          高德
                          {message.read_tools.route.result.mode === "walk"
                            ? "步行"
                            : "驾车"}
                          路线
                        </strong>
                        <p>
                          {message.read_tools.route.result.distance_meters <
                          1000
                            ? `${message.read_tools.route.result.distance_meters} 米`
                            : `${(message.read_tools.route.result.distance_meters / 1000).toFixed(1)} 公里`}{" "}
                          · 预计{" "}
                          {Math.ceil(
                            message.read_tools.route.result.duration_seconds /
                              60,
                          )}{" "}
                          分钟
                        </p>
                        <small>供应商估计用时 · 非实时导航</small>
                        {message.context?.route_request && (
                          <Link
                            state={{ from: "/assistant" }}
                            to={`/places/${encodeURIComponent(message.context.route_request.destination_place_id)}/route?origin_place_id=${encodeURIComponent(message.context.route_request.origin_place_id)}&mode=${message.context.route_request.mode}`}
                          >
                            打开路线地图 <ArrowUpRight size={13} />
                          </Link>
                        )}
                      </>
                    ) : (
                      <p>路线暂不可用，请稍后重试或在地点详情中查询路线。</p>
                    )}
                  </div>
                )}
                {message.companion_result && (
                  <CompanionThinking result={message.companion_result} />
                )}
                {!!message.companion_result?.suggestions.length &&
                  !message.place_cards?.length && (
                    <div className="travel-assistant-suggestions">
                      {message.companion_result.suggestions
                        .slice(0, 4)
                        .map((suggestion) => (
                          <button
                            key={suggestion.suggestion_id}
                            disabled={busy}
                            onClick={() =>
                              assistant.setDraft(
                                `展开说说：${suggestion.title}`,
                              )
                            }
                          >
                            {suggestion.title}
                            <ArrowUpRight size={13} />
                          </button>
                        ))}
                    </div>
                  )}
              </div>
            </div>
          </div>
        ))}
        {assistant.submission && (
          <div className="travel-assistant-turn">
            <div className="travel-assistant-user">{assistant.submission}</div>
            <div className="travel-assistant-reply">
              <Sparkles size={17} />
              <div className="travel-assistant-text">
                {assistant.stream || assistant.status}
              </div>
            </div>
          </div>
        )}
        {error && (
          <div className="travel-assistant-error" role="alert">
            <p>{error}</p>
            {!session && (
              <button onClick={assistant.retrySession}>重新连接</button>
            )}
            <p>
              你仍可以<Link to="/explore">继续探索</Link>，或查看
              <Link to="/favorites">我的收藏</Link>。
            </p>
          </div>
        )}
        <div ref={end} />
      </div>
      {(context.place || messages.length > 0) && <RelatedPlaces />}
      <form
        className="travel-assistant-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void assistant.send();
        }}
      >
        <label
          className="sr-only"
          htmlFor={
            drawer ? "drawer-assistant-message" : "page-assistant-message"
          }
        >
          告诉助手你的旅行想法
        </label>
        <textarea
          id={drawer ? "drawer-assistant-message" : "page-assistant-message"}
          value={draft}
          onChange={(event) => assistant.setDraft(event.target.value)}
          placeholder="想去哪，或有什么旅行问题？"
          rows={2}
          maxLength={6000}
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
          }}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing &&
              !composing.current &&
              event.keyCode !== 229
            ) {
              event.preventDefault();
              if (!event.repeat) void assistant.send();
            }
          }}
        />
        <button
          type="submit"
          disabled={!draft.trim() || busy || loading || !session}
          aria-label={busy ? "正在回答" : "发送消息"}
        >
          <ArrowUp size={20} />
        </button>
      </form>
      <footer className="travel-assistant-footer">
        AI 建议仅供参考 · 此处的浏览与讨论不会修改正式旅行
      </footer>
    </div>
  );
}

function RelatedPlaces() {
  const { context, session, draft, exploreRepository } = useTravelAssistant();
  const [expanded, setExpanded] = useState(false);
  const [city, setCity] = useState(context.place?.city ?? "");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ExplorePlace[]>([]);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);
  const requestId = useRef(0);
  useEffect(() => {
    requestId.current += 1;
    setCity(context.place?.city ?? "");
    setQuery("");
    setResults([]);
    setSearched(false);
    setError("");
    setSearching(false);
  }, [context.place?.id, context.place?.city, context.tripId]);
  const search = async () => {
    if (!city.trim() || !query.trim()) return;
    const id = ++requestId.current;
    setSearching(true);
    setError("");
    setResults([]);
    try {
      const response = await exploreRepository.search({
        city: city.trim(),
        q: query.trim(),
        category: "all",
      });
      if (id === requestId.current) {
        setResults(response.items.slice(0, 4));
        setSearched(true);
      }
    } catch (cause) {
      if (id === requestId.current) setError(messageOf(cause));
    } finally {
      if (id === requestId.current) setSearching(false);
    }
  };
  return (
    <details
      className="travel-assistant-related"
      open={expanded}
      onToggle={(event) => {
        const open = event.currentTarget.open;
        setExpanded(open);
        if (open && !query)
          setQuery(
            context.place?.name ??
              (draft.trim() || topicMessages(session).at(-1)?.user || ""),
          );
      }}
    >
      <summary>
        <MapPin size={14} />
        查看相关地点<span>搜索真实地点</span>
      </summary>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void search();
        }}
      >
        <label>
          目的地城市
          <input
            value={city}
            placeholder="例如：成都"
            onChange={(event) => setCity(event.target.value)}
          />
        </label>
        <label>
          地点关键词
          <input
            value={query}
            placeholder="地点名或感兴趣的体验"
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button disabled={searching || !city.trim() || !query.trim()}>
          {searching ? "查找中…" : "查找地点"}
        </button>
      </form>
      {error && (
        <p role="alert">
          {error} <Link to="/explore">继续探索</Link>
        </p>
      )}
      {searched && !results.length && !searching && (
        <p>没有匹配的地点，试试更具体的名称或换个关键词。</p>
      )}
      {results.length > 0 && (
        <ul>
          {results.map((place) => (
            <li key={place.id}>
              <Link
                state={{ from: "/assistant" }}
                to={`/places/${encodeURIComponent(place.id)}`}
              >
                {place.name}
                <ArrowUpRight size={13} />
              </Link>
              <small>
                {place.city} · {place.address}
              </small>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

function messageOf(cause: unknown) {
  return cause instanceof Error
    ? cause.message
    : "助手暂时无法回答，请稍后重试。";
}
