package f1zoom.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
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

@RestController                 // Handle HTTP requests and convert Java to JSON
@RequestMapping("/api/v1")      // Base path
@CrossOrigin(origins = "*")     // Fixes CORS (Cross-origin Resource Sharing) errors. Allow any website to call the API *. For production specify website
public class F1Controller {

    // Spring HTTP client - makes HTTP request to other APIs
    private final RestTemplate restTemplate = new RestTemplate();
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${supabase.url:}")
    private String supabaseUrl;

    @Value("${supabase.service-role-key:}")
    private String supabaseServiceRoleKey;

    // Create endpoint  GET /api/v1/test
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

    // 6. Circuit + session data from Supabase for a season
    @GetMapping("/circuits/season/{season}")
    public Object getCircuitsForSeason(@PathVariable int season) {
        try {
            Map<Long, Map<String, Object>> circuitsById = new LinkedHashMap<>();

            Map<String, String> circuitsParams = new LinkedHashMap<>();
            circuitsParams.put("select", "id,code,file_slug,title,subtitle,flag,weekend_format,length_km,laps,corners,distance_km");
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

            Map<String, String> eventsParams = new LinkedHashMap<>();
            eventsParams.put("select", "id,season,round,grand_prix_name,circuit_id,race_sessions(session_type,session_date_aest,session_time_aest)");
            eventsParams.put("season", "eq." + season);
            eventsParams.put("order", "round.asc");
            JsonNode eventsNode = supabaseGet("race_events", eventsParams);

            List<Map<String, Object>> result = new ArrayList<>();
            Set<Long> seenCircuitIds = new HashSet<>();

            for (JsonNode event : eventsNode) {
                long circuitId = event.path("circuit_id").asLong(-1);
                Map<String, Object> circuit = circuitsById.get(circuitId);
                if (circuit == null) continue;

                Map<String, Object> row = new LinkedHashMap<>(circuit);
                row.put("season", event.path("season").asInt());
                row.put("round", event.path("round").asInt());
                row.put("grandPrixName", textOrNull(event, "grand_prix_name"));
                row.put("sessions", parseSessions(event.path("race_sessions")));

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
                    result.add(row);
                }
            }

            return result;
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Failed to load circuits from Supabase", e);
        }
    }

    // 7. AI Prediction model for Next Race winner endpoint
    // AI prediction - placeholder
    @GetMapping("/predictions/next-race")
    public Map<String, Object> getNextRacePrediction() {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "model_in_progress");
        response.put("predictedWinner", "TBD");
        return response;
    }

    private JsonNode supabaseGet(String table, Map<String, String> queryParams) throws Exception {
        if (supabaseUrl == null || supabaseUrl.isBlank() || supabaseServiceRoleKey == null || supabaseServiceRoleKey.isBlank()) {
            throw new IllegalStateException("Supabase credentials missing. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY for read-only access).");
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
            String.class
        );

        return objectMapper.readTree(response.getBody());
    }

    private List<Map<String, Object>> parseSessions(JsonNode sessionsNode) {
        List<Map<String, Object>> sessions = new ArrayList<>();
        if (sessionsNode == null || !sessionsNode.isArray()) return sessions;

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
            String sessionType = textOrNull(session, "session_type");
            String sessionDateAest = textOrNull(session, "session_date_aest");
            String sessionTimeAest = textOrNull(session, "session_time_aest");

            Map<String, Object> item = new LinkedHashMap<>();
            item.put("sessionType", sessionType);
            item.put("sessionDateAest", sessionDateAest);
            item.put("sessionTimeAest", sessionTimeAest);
            item.put("sessionStartUtc", buildSessionStartUtc(sessionDateAest, sessionTimeAest));
            sessions.add(item);
        }

        return sessions;
    }

    private String buildSessionStartUtc(String dateAest, String timeAest) {
        if (dateAest == null || dateAest.isBlank() || timeAest == null || timeAest.isBlank()) {
            return null;
        }
        try {
            LocalDate date = LocalDate.parse(dateAest);
            LocalTime time = LocalTime.parse(timeAest);
            return ZonedDateTime.of(date, time, ZoneId.of("Australia/Brisbane")).toInstant().toString();
        } catch (Exception ignored) {
            return null;
        }
    }

    private String textOrNull(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (value.isMissingNode() || value.isNull()) return null;
        String text = value.asText();
        return text == null || text.isBlank() ? null : text;
    }
}
