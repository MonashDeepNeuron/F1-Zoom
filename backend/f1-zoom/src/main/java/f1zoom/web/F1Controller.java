package f1zoom.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.util.UriComponentsBuilder;

@RestController // Handle HTTP requests and convert Java to JSON
@RequestMapping("/api/v1") // Base path
@CrossOrigin(origins = "*") // Fixes CORS (Cross-origin Resource Sharing) errors. Allow any website to call
                            // the API *. For production specify website
public class F1Controller {

    // Spring HTTP client - makes HTTP request to other APIs
    private final RestTemplate restTemplate = new RestTemplate();
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${supabase.url:}")
    private String supabaseUrl;

    @Value("${supabase.service-role-key:}")
    private String supabaseServiceRoleKey;

    // Create endpoint GET /api/v1/test
    @GetMapping("/test")
    public String test() {
        return "F1 Zoom API is working";
    }

    // 1. Drivers Championship Standings endpoint
    @GetMapping("/championship/drivers")
    public Object getDriverStandings() {
        // URL of external API
        String url = "https://api.jolpi.ca/ergast/f1/2025/driverStandings.json";
        // Make HTTP GET request and return what's sent back
        return restTemplate.getForObject(url, Object.class);
    }

    // 2. Constructors Standings endpoint
    @GetMapping("/championship/constructors")
    public Object getConstructorStandings() {
        String url = "https://api.jolpi.ca/ergast/f1/2025/constructorStandings.json";
        return restTemplate.getForObject(url, Object.class);
    }

    // 3. Next Race Info endpoint
    @GetMapping("/races/next")
    public Object getNextRace() {
        String url = "https://api.jolpi.ca/ergast/f1/current/next.json";
        return restTemplate.getForObject(url, Object.class);
    }

    // 4. Last Race Info endpoint
    @GetMapping("/races/last")
    public Object getLastRace() {
        String url = "https://api.jolpi.ca/ergast/f1/current/last/results.json";
        return restTemplate.getForObject(url, Object.class);
    }

    // 5. Current season schedule endpoint
    @GetMapping("/races/schedule")
    public Object getRaceSchedule() {
        String url = "https://api.jolpi.ca/ergast/f1/current.json";
        return restTemplate.getForObject(url, Object.class);
    }

    // 6. Full Season Calendar endpoint (alias for schedule)
    @GetMapping("/races/calendar")
    public Object getRaceCalendar() {
        String url = "https://api.jolpi.ca/ergast/f1/current.json";
        return restTemplate.getForObject(url, Object.class);
    }

    // 7. Circuit + session data from Supabase for a season
    @GetMapping("/circuits/season/{season}")
    public Object getCircuitsForSeason(@PathVariable int season) {
        try {
            Map<Long, Map<String, Object>> circuitsById = new LinkedHashMap<>();

            Map<String, String> circuitsParams = new LinkedHashMap<>();
            circuitsParams.put("select",
                    "id,code,file_slug,title,subtitle,flag,weekend_format,length_km,laps,corners,distance_km");
            circuitsParams.put("order", "id.asc");
            JsonNode circuitsNode = supabaseGet("circuits", circuitsParams);

            for (JsonNode circuit : circuitsNode) {
                Map<String, Object> item = new LinkedHashMap<>();
                long id = circuit.path("id").asLong();
                item.put("id", id);
                item.put("code", textOrNull(circuit, "code"));
                item.put("fileSlug", textOrNull(circuit, "file_slug"));
                item.put("title", textOrNull(circuit, "title"));
                item.put("subtitle", textOrNull(circuit, "subtitle"));
                item.put("flag", textOrNull(circuit, "flag"));
                item.put("weekendFormat", textOrNull(circuit, "weekend_format"));
                item.put("lengthKm", circuit.path("length_km").asDouble());
                item.put("laps", circuit.path("laps").asInt());
                item.put("corners", circuit.path("corners").asInt());
                item.put("distanceKm", circuit.path("distance_km").asDouble());
                circuitsById.put(id, item);
            }

            // Fetch track history (past winners) grouped by circuit_id
            Map<Long, List<Map<String, Object>>> historyByCircuit = new LinkedHashMap<>();
            try {
                Map<String, String> historyParams = new LinkedHashMap<>();
                historyParams.put("select", "circuit_id,year,winner");
                historyParams.put("order", "year.desc");
                JsonNode historyNode = supabaseGet("track_history", historyParams);

                for (JsonNode row : historyNode) {
                    long circuitId = row.path("circuit_id").asLong(-1);
                    Map<String, Object> entry = new LinkedHashMap<>();
                    entry.put("year", row.path("year").asInt());
                    entry.put("winner", textOrNull(row, "winner"));
                    historyByCircuit.computeIfAbsent(circuitId, k -> new ArrayList<>()).add(entry);
                }
            } catch (Exception ignored) {
                // track_history table may not exist yet; silently continue with empty history
            }

            Map<String, String> eventsParams = new LinkedHashMap<>();
            eventsParams.put("select",
                    "id,season,round,grand_prix_name,circuit_id,race_sessions(session_type,session_start_utc)");
            eventsParams.put("season", "eq." + season);
            eventsParams.put("order", "round.asc");
            JsonNode eventsNode = supabaseGet("race_events", eventsParams);

            List<Map<String, Object>> result = new ArrayList<>();
            Set<Long> seenCircuitIds = new HashSet<>();

            for (JsonNode event : eventsNode) {
                long circuitId = event.path("circuit_id").asLong(-1);
                Map<String, Object> circuit = circuitsById.get(circuitId);
                if (circuit == null)
                    continue;

                Map<String, Object> row = new LinkedHashMap<>(circuit);
                row.put("season", event.path("season").asInt());
                row.put("round", event.path("round").asInt());
                row.put("grandPrixName", textOrNull(event, "grand_prix_name"));
                row.put("sessions", parseSessions(event.path("race_sessions")));
                row.put("history", historyByCircuit.getOrDefault(circuitId, new ArrayList<>()));

                result.add(row);
                seenCircuitIds.add(circuitId);
            }

            for (Map.Entry<Long, Map<String, Object>> entry : circuitsById.entrySet()) {
                if (!seenCircuitIds.contains(entry.getKey())) {
                    Map<String, Object> row = new LinkedHashMap<>(entry.getValue());
                    row.put("season", season);
                    row.put("round", null);
                    row.put("grandPrixName", null);
                    row.put("sessions", new ArrayList<>());
                    row.put("history", historyByCircuit.getOrDefault(entry.getKey(), new ArrayList<>()));
                    result.add(row);
                }
            }

            return result;
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Failed to load circuits from Supabase",
                    e);
        }
    }

    // 8. AI Prediction model for Next Race winner endpoint
    @GetMapping("/predictions/next-race")
    public Map<String, Object> getNextRacePrediction() {
        try {
            // Call Python FastAPI prediction service
            RestTemplate restTemplate = new RestTemplate();
            String pythonServiceUrl = "http://localhost:8000/predict/next-race";

            ResponseEntity<Map> response = restTemplate.getForEntity(
                    pythonServiceUrl,
                    Map.class);

            if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
                return response.getBody();
            } else {
                throw new Exception("Prediction service returned non-2xx status");
            }

        } catch (Exception e) {
            // Fallback response if Python service is unavailable
            Map<String, Object> fallback = new HashMap<>();
            fallback.put("status", "service_unavailable");
            fallback.put("predictedWinner", "TBD");
            fallback.put("confidence", "N/A");
            fallback.put("message", "Prediction service is not running. Start it with: python prediction_service.py");
            return fallback;
        }
    }

    private JsonNode supabaseGet(String table, Map<String, String> queryParams) throws Exception {
        if (supabaseUrl == null || supabaseUrl.isBlank() || supabaseServiceRoleKey == null
                || supabaseServiceRoleKey.isBlank()) {
            throw new IllegalStateException(
                    "Supabase credentials missing. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY for read-only access).");
        }

        UriComponentsBuilder builder = UriComponentsBuilder
                .fromUriString(supabaseUrl)
                .pathSegment("rest", "v1", table);

        for (Map.Entry<String, String> entry : queryParams.entrySet()) {
            builder.queryParam(entry.getKey(), entry.getValue());
        }

        HttpHeaders headers = new HttpHeaders();
        headers.set("apikey", supabaseServiceRoleKey);
        headers.setBearerAuth(supabaseServiceRoleKey);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        HttpEntity<Void> requestEntity = new HttpEntity<>(headers);
        ResponseEntity<String> response = restTemplate.exchange(
                builder.build(true).toUri(),
                HttpMethod.GET,
                requestEntity,
                String.class);

        return objectMapper.readTree(response.getBody());
    }

    private List<Map<String, Object>> parseSessions(JsonNode sessionsNode) {
        List<Map<String, Object>> sessions = new ArrayList<>();
        if (sessionsNode == null || !sessionsNode.isArray())
            return sessions;

        Map<String, Integer> sessionOrder = new HashMap<>();
        sessionOrder.put("practice_1", 1);
        sessionOrder.put("practice_2", 2);
        sessionOrder.put("practice_3", 3);
        sessionOrder.put("sprint_qualifying", 4);
        sessionOrder.put("qualifying", 5);
        sessionOrder.put("sprint", 6);
        sessionOrder.put("race", 7);

        List<JsonNode> rawSessions = new ArrayList<>();
        for (JsonNode session : sessionsNode) {
            rawSessions.add(session);
        }

        rawSessions.sort((a, b) -> {
            String aType = textOrNull(a, "session_type");
            String bType = textOrNull(b, "session_type");
            int aOrder = sessionOrder.getOrDefault(aType, 999);
            int bOrder = sessionOrder.getOrDefault(bType, 999);
            return Integer.compare(aOrder, bOrder);
        });

        for (JsonNode session : rawSessions) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("sessionType", textOrNull(session, "session_type"));
            item.put("sessionStartUtc", textOrNull(session, "session_start_utc"));
            sessions.add(item);
        }

        return sessions;
    }

    private String textOrNull(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (value.isMissingNode() || value.isNull())
            return null;
        String text = value.asText();
        return text == null || text.isBlank() ? null : text;
    }
}
