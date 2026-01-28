package f1zoom.web;

import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.bind.annotation.GetMapping;




@RestController                 // Handle HTTP requests and convert Java to JSON
@RequestMapping("/api/v1")      // Base path
@CrossOrigin(origins = "*")     // Fixes CORS (Cross-origin Resource Sharing) errors. Allow any website to call the API *. For production specify website
public class F1Controller {

    // Spring HTTP client - makes HTTP request to other APIs
    private final RestTemplate restTemplate = new RestTemplate();

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

    // 5. AI Prediction model for Next Race winner endpoint
    
}
