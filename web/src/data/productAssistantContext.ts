import type {
  ExplorePlace,
  ExplorePoint,
  ExploreCategory,
} from "../domain/explore";

// One browser-owned topic is shared by the contextual and full conversation surfaces.
// It avoids importing unrelated stage-two test conversations into a first visit.
export function assistantTopic(): string {
  if (import.meta.env.VITE_DISCOVERY_PRODUCT !== "true") return "travel-main";
  try {
    let topic = localStorage.getItem("roamsync.discovery.topic");
    if (!topic) {
      topic = `discovery-${crypto.randomUUID()}`;
      localStorage.setItem("roamsync.discovery.topic", topic);
    }
    return topic;
  } catch {
    return "discovery-product";
  }
}

export interface AssistantDiscoveryContext {
  city?: string;
  query?: string;
  category?: ExploreCategory;
  center: ExplorePoint;
  radius_meters: number;
  min_rating?: number;
  max_food_price_yuan?: number;
  include_unknown: boolean;
}
export interface AssistantProductReadContext {
  place?: ExplorePlace;
  places?: ExplorePlace[];
  tripId?: string;
  city?: string;
  discovery?: AssistantDiscoveryContext;
  draftContext?: {
    draftId: string;
    version: number;
    city: string;
    requirements?: string;
    plan?: unknown;
  };
  surface?:
    "execution" | "trip" | "draft" | "map" | "place" | "explore" | "assistant";
}

export type AssistantContextContract =
  "product-preview" | "assistant-context-v1";

// D switches to C's contract after B's canonical UUID Place adapter is wired.
export function productAssistantContext(
  context: AssistantProductReadContext,
  contract: AssistantContextContract = "product-preview",
) {
  const place = context.place;
  if (contract === "assistant-context-v1") {
    if (
      [place, ...(context.places ?? [])]
        .filter(Boolean)
        .some(
          (p) =>
            p &&
            !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
              p.id,
            ),
        )
    ) {
      throw new Error("当前地点身份尚未接入统一地点服务，请先使用自由对话。");
    }
    const browsingCity = place?.city ?? context.city ?? context.draftContext?.city ?? null;
    const freeAssistant = !place && !context.tripId && !context.draftContext && !context.discovery
      && (!context.surface || context.surface === "assistant");
    return {
      context: {
        version: "assistant-context-v1",
        topic_id: assistantTopic(),
        surface:
          context.surface ??
          (place
            ? "place"
            : context.draftContext
              ? "draft"
              : context.tripId
                ? "trip"
                : context.discovery
                  ? "map"
                  : "assistant"),
        // Omission continues the server-read conversational city; explicit null
        // on other surfaces retains its existing scope-clearing meaning.
        ...(!freeAssistant || browsingCity ? { browsing_city: browsingCity } : {}),
        discussing_place_id: place?.id ?? null,
        read_trip_id: context.tripId ?? null,
        ...(import.meta.env.VITE_DISCOVERY_PRODUCT === "true"
          ? {
              discussing_place_ids: [
                ...new Set((context.places ?? []).map((p) => p.id)),
              ].slice(0, 8),
            }
          : context.places?.length
            ? {
                discussing_place_ids: [
                  ...new Set(context.places.map((p) => p.id)),
                ].slice(0, 8),
              }
            : {}),
        ...(context.discovery
          ? {
              discovery_context: {
                ...context.discovery,
                query: context.discovery.query ?? "",
                category: (
                  {
                    sight: "attraction",
                    hotel: "lodging",
                    food: "food",
                    all: "all",
                  } as const
                )[context.discovery.category ?? "all"],
                center: {
                  ...context.discovery.center,
                  coordinate_system: "gcj02",
                },
              },
            }
          : {}),
        ...(context.draftContext
          ? {
              read_draft_id: context.draftContext.draftId,
              read_draft_version: context.draftContext.version,
            }
          : import.meta.env.VITE_DISCOVERY_PRODUCT === "true"
            ? { read_draft_id: null, read_draft_version: null }
            : {}),
        ...(!context.discovery &&
        import.meta.env.VITE_DISCOVERY_PRODUCT === "true"
          ? { discovery_context: null }
          : {}),
        physical_location: null,
        action_target: null,
      },
    };
  }
  return {
    read_context: {
      surface: "explore",
      ...(context.tripId ? { trip_id: context.tripId } : {}),
      ...(place
        ? {
            place: {
              id: place.id,
              name: place.name,
              city: place.city,
              address: place.address,
            },
          }
        : {}),
    },
  };
}
