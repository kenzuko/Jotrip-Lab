/* JoTrip Operations Dashboard
 * READ-ONLY integration contract.
 * Existing backend data MUST NOT be mutated from this page.
 * Fill an endpoint only when its existing GET contract is known and approved.
 */
window.JOTRIP_OPS_CONFIG = Object.freeze({
  appName: "JoTrip Operations Center",
  timezone: "Asia/Ho_Chi_Minh",
  readOnly: true,
  demoQueryParam: "demo",
  fetchTimeoutMs: 10000,
  sources: Object.freeze({
    weather: "../weather/dashboard-data.json",
    airQuality: "../weather/air-quality.json",
    tide: "../weather/tide.json",
    flights: "../data/sunairport/latest.json",

    // Existing JoTrip backend adapters.
    // Keep null until the exact GET endpoint is known.
    // The dashboard never POSTs, PUTs, PATCHes or DELETEs to these.
    ferries: null,
    tours: null,
    bookings: null,
    customers: null,
    partners: null,
    staff: null,
    tasks: null,
    alerts: null,
    shifts: null
  })
});
