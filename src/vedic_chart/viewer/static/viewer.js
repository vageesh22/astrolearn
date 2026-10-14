/* Layers 14 and 15: the page.
 *
 * Plain ES2020, no framework, no bundler, no network except this server's own
 * three files and two POSTs: one to /api/chart per submission and one to
 * /api/places per settled keystroke.
 *
 * What this file may not do, and does not (Layer 14 sections 9.1 and 13.3): it
 * builds no date object, converts no transported value into a numeric type,
 * performs no arithmetic on a transported string, knows no timezone rule, and
 * computes no boundary, fraction, membership or offset. Every timestamp, every
 * fraction, every coordinate and both birth chains arrive as strings that
 * Python already formatted; the page nests rows by their `level`, orders them
 * by array order, reads membership off the `N`/`Q` flags, and displays text.
 *
 * Layer 15 adds three things and takes one away. The birthplace field is an
 * ARIA combobox whose suggestions come from the server, which also normalises
 * the query: this file decides only on the raw length of the text before the
 * first comma and never reimplements a normalisation of its own. The time and
 * the birthplace may be left blank, and a result then says, in Python's own
 * wording, which values were assumed. The daśā year convention is no longer a
 * control at all -- the server fixes it and sends the sentence to print.
 *
 * It also uses no browser storage of any kind and inserts every dynamic string
 * with `textContent`; no markup-parsing property is ever assigned. The single
 * exception to "text only" is the SVG, which is parsed with `DOMParser`,
 * checked, and adopted -- inline rather than as an image, so that the
 * renderer's own `role="img"`, title and description stay available to
 * assistive technology.
 *
 * The forbidden API names of Layer 14 section 13.3 are deliberately absent from
 * this file altogether, comments included, because the scan that enforces them
 * is textual.
 *
 * Layer 19 adds a display preference, the "Chart style" radio group: North
 * Indian (the default), South Indian, or Both. Every applied document carries
 * both SVGs and both are inserted on arrival, so a switch only shows and hides
 * what the page already holds -- no request, no re-parse, no recalculation. The
 * preference is a variable of this script and nothing else: it is not
 * persisted anywhere and a reload returns to North Indian.
 *
 * Layer 20 adds the "Show transits" overlay. A transit chart is an ordinary
 * chart for another instant: the third request of this file goes to the same
 * /api/chart endpoint with the same four-key body, headers and options as the
 * natal one, for the natal document's own place record. The page lays the
 * nine transit grahas over the natal frame *by sign*, copying every
 * coordinate, font size and degree text as a string from the two documents'
 * `overlay` blocks; it compares those strings with regular expressions and
 * `===` only, counts with `.length`, and still converts nothing transported
 * into a number. The overlay is requested only on an explicit action (the
 * toggle turned on, or Update); there is no clock, no "now", no polling and no
 * repeating timer of any kind -- the interval-timer API is named nowhere in
 * this file, for the same textual-scan reason as above. Exactly one completed
 * transit result is kept, in page memory, and nothing is stored anywhere.
 */

(function () {
  "use strict";

  var SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  var LEVEL_ABBR = ["", "MD", "AD", "PD"];
  var LEVEL_WORD = ["", "Mahadasha", "Antardasha", "Pratyantardasha"];
  var CHAIN_SEPARATOR = " › ";
  var SET_SIZE = "9";

  /* Layer 14 section 6: the two renderer labels are matched by exact string,
   * and any descriptor this page has no label for is shown as the descriptor
   * itself. Nothing is inferred from a value the engine did not send. */
  var HOUSE_LABELS = { whole_sign: "Whole Sign" };
  var NODE_LABELS = { mean: "Mean Node" };

  var ERROR_TITLES = {
    input: "Check the birth details",
    dasha_range: "That birth is outside the daśā cycle's range",
    place_not_found: "No such birthplace record",
    place_selection_required: "Choose a birthplace from the list",
    stale_schema: "This page is out of date",
    resource: "A configured resource could not be read",
    unexpected: "The calculation did not complete",
    forbidden: "The server refused the request",
    bad_request: "The server refused the request",
    length_required: "The server refused the request",
    payload_too_large: "The server refused the request",
    unsupported_media_type: "The server refused the request",
    request_timeout: "The request timed out",
    not_found: "The server has no such endpoint",
    method_not_allowed: "The server has no such endpoint"
  };

  var DIVERGENCE_NOTE =
    "The nominal and quantized birth chains differ. N marks the chain " +
    "defined by the Moon's exact nakṣatra fraction; Q marks the chain whose " +
    "quantized microsecond intervals contain the birth timestamp. They " +
    "differ only when a post-birth remainder is shorter than one microsecond " +
    "(Layer 12 §7).";

  var HALF_OPEN_NOTE = "Intervals are half-open [start, end).";
  var PRE_BIRTH_NOTE =
    "The first Mahadasha begins at or before birth (before birth unless the " +
    "core's elapsed nakshatra fraction is zero); its pre-birth part is listed.";

  /* Layer 19 sections 5.6 and 6: the three display preferences, the three
   * states of the South Indian document, and the two notices shown in its
   * block when it cannot be displayed. */
  var STYLE_NORTH = "north";
  var STYLE_SOUTH = "south";
  var STYLE_BOTH = "both";
  var SOUTH_PRESENT = "present";
  var SOUTH_MISSING = "missing";
  var SOUTH_REJECTED = "rejected";
  var SOUTH_MISSING_NOTICE =
    "The South Indian chart is not available from this server's response; " +
    "the North Indian chart is shown instead.";
  var SOUTH_REJECTED_NOTICE =
    "The South Indian chart could not be shown: the server's document was " +
    "not one this page accepts; the North Indian chart is shown instead.";

  /* Layer 20 sections 5 and 6.7: the overlay's vocabulary. Every value the
   * page draws comes from a document; these are only the names it checks
   * against and the one colour of section 5.1. */
  var OVERLAY_SCHEMA = "vedic_chart.overlay/1";
  var POSITIONS_SCHEMA = "vedic_chart.planetary_positions/1";
  var META_NONE = "none";
  var META_OK = "ok";
  var META_MISSING = "missing";
  var META_MALFORMED = "malformed";
  var LAYOUT_INLINE = "inline";
  var LAYOUT_STACKED = "stacked";
  var MARKER_ANCHORS = ["start", "middle", "end"];
  var FLOOR_FONT = "21.00";
  var TRANSIT_FILL = "#c2410c";
  var TRANSIT_COUNT = 9;
  var SIGN_KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"];
  var SIGN_NUMBERS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
  var COORDINATE_SYNTAX = /^[0-9]+\.[0-9]{2}$/;
  var DEGREE_TEXT_SYNTAX = /^[0-9]{1,2}°[0-9]{2}′$/;
  var COUNT_SYNTAX = /^[0-9]+$/;
  var NORTH_PREFIX = "d1";
  var SOUTH_PREFIX = "d1-south";
  var TRANSIT_UNAVAILABLE_SOUTH = "South Indian chart not available";
  var PANEL_ONLY_TEXT = "panel only — no room for marker";
  var PANEL_ONLY_SENTENCE = "Some transit entries appear in the panel only.";
  var CALCULATING_TRANSITS = "Calculating transits…";
  var INCOMPLETE_TRANSIT = "Enter a transit date and time.";
  var NATAL_STALE_TRANSIT = "Natal inputs changed — generate the natal chart first.";
  var NEW_NATAL_TRANSIT = "Press Update to show transits for the new natal chart.";
  var TRANSITS_OFF = "Transits off.";

  /* Layer 15 section 3: one badge wording, shown beside three headings. */
  var ASSUMED_BADGE = "Uses assumed birth details";

  /* Layer 15 section 2 rule 3, verbatim: the one sentence the page shows when a
   * birthplace was typed but no suggestion was chosen. The server answers the
   * same case with its own `place_selection_required` sentence. */
  var SELECTION_PROMPT =
    "Select a suggestion from the list, or clear the field to use the " +
    "default birthplace.";

  var STALE_SCHEMA_SENTENCE =
    "This page is out of date: reload it to continue.";
  var STALE_SCHEMA_HINT =
    "Reload the page in the browser and submit again; nothing was calculated.";

  var DATE_SYNTAX = /^[0-9]{4}-[0-9]{2}-[0-9]{2}$/;
  var TIME_SYNTAX = /^[0-9]{2}:[0-9]{2}(:[0-9]{2})?$/;
  var EVENT_HANDLER_ATTRIBUTE = /^on/i;

  /* Layer 15 section 5.2: the debounce, and the raw-length threshold. The
   * threshold is a count of code points before the first comma -- a length, not
   * a normalisation: what actually matches is the server's business. */
  var SUGGEST_DELAY = 150;
  var SUGGEST_MINIMUM = 2;

  /* Which error kinds name which field (Layer 14 section 10.1 as Layer 15
   * section 8 extends it). The message is matched only to pick the field to
   * focus; the `kind` is what decides everything else. */
  var PLACE_WORDS = /place_id|birthplace|identifier|label|record/i;
  var TIME_WORDS = /\btime\b/i;

  /* --- element handles ---------------------------------------------- */

  var token = "";
  var tokenMeta = document.querySelector('meta[name="viewer-token"]');
  if (tokenMeta) {
    token = tokenMeta.getAttribute("content") || "";
  }

  /* Layer 15 section 4.2: the configured default birthplace, as
   * "<id>|<label>". Split on the **first** separator only, because a label is
   * free text from the geodata database and a pipe in it must not become a
   * second field. */
  var defaultPlaceLabel = "";
  var defaultMeta = document.querySelector('meta[name="viewer-default-place"]');
  if (defaultMeta) {
    var defaultText = defaultMeta.getAttribute("content") || "";
    var separator = defaultText.indexOf("|");
    defaultPlaceLabel =
      separator === -1 ? defaultText : defaultText.slice(separator + 1);
  }

  var form = document.getElementById("birth-form");
  var dateField = document.getElementById("birth-date");
  var timeField = document.getElementById("birth-time");
  var placeField = document.getElementById("birth-place");
  var placeIdField = document.getElementById("place-id");
  var placeListbox = document.getElementById("place-listbox");
  var placeMarker = document.getElementById("place-marker");
  var formNote = document.getElementById("form-note");
  var generateButton = document.getElementById("generate");
  var cancelButton = document.getElementById("cancel");
  var statusRegion = document.getElementById("status");
  var alertRegion = document.getElementById("alert");
  var resultsRegion = document.getElementById("results");
  var resultsBody = document.getElementById("results-body");
  var resultsTemplate = document.getElementById("results-template");
  var mainRegion = document.querySelector(".v-main");
  var styleGroup = document.getElementById("chart-style");
  var styleInputs = [
    document.getElementById("chart-style-north"),
    document.getElementById("chart-style-south"),
    document.getElementById("chart-style-both")
  ];

  /* Layer 20 section 3.1: the transit control, outside the form. */
  var transitGroup = document.getElementById("transit");
  var transitToggle = document.getElementById("transit-toggle");
  var transitDateField = document.getElementById("transit-date");
  var transitTimeField = document.getElementById("transit-time");
  var transitUpdate = document.getElementById("transit-update");
  var transitPlace = document.getElementById("transit-place");
  var transitStatus = document.getElementById("transit-status");

  var fieldMessages = {
    date: document.getElementById("birth-date-message"),
    time: document.getElementById("birth-time-message"),
    place_text: document.getElementById("birth-place-message")
  };

  /* --- page state ---------------------------------------------------- */

  var sequence = 0;
  var inFlight = null;
  var cancelledSequence = -1;

  var shown = null;

  /* Layer 19 section 6.2: the selected chart style. Read by `applyStyle`,
   * written only by the radio group's `change` event. */
  var chartStyle = STYLE_NORTH;

  /* Layer 20 section 6.4: the transit state. `transitOn` mirrors the
   * checkbox and is written only by its own `change` event (and set off when
   * the overlay metadata is unusable); a response never sets it.
   * `transitSequence` is bumped by every request AND every invalidation.
   * `transitPending` is the ONE owned request, or null:
   *   {key: {natal, date, time}, captured: {date, time, place_text, place_id},
   *    sequence, controller}
   * `transitResult` is the ONE retained completed result, or null:
   *   {key: {natal, date, time}, planets, entries, offset,
   *    groups: {north: <g>|null, south: <g>|null}, panelRows, statusText}
   * `transitFailure` is {key, kind, message, statusText} of the last failed
   * owned attempt. `overlayMeta` says whether the shown natal document's
   * `overlay` block is usable. `natalLoading` is true while a natal request
   * is in flight. */
  var transitOn = false;
  var transitSequence = 0;
  var transitPending = null;
  var transitResult = null;
  var transitFailure = null;
  var overlayMeta = META_NONE;
  var overlayProblem = "";
  var natalLoading = false;

  /* The composition fault seam of Layer 20 section 10.8; null unless the page
   * was opened with #acceptance (see the seam at the end of this file). */
  var composeFault = null;

  /* The combobox's own state (Layer 15 section 5.2). `placeSequence` is bumped
   * by every input event, every clear and every selection -- at once, not when
   * the next request starts -- so a response that arrives late can be
   * recognised as obsolete and dropped. */
  var placeSequence = 0;
  var placeInFlight = null;
  var placeTimer = null;
  var placeOptions = [];
  var placeActive = -1;

  /* True only between a pointer press on Generate or Cancel and its release;
   * see `onPlaceBlur`. */
  var pointerOnAction = false;

  /* --- small DOM helpers --------------------------------------------- */

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = text;
    }
    return node;
  }

  function setText(node, text) {
    if (node) {
      node.textContent = text;
    }
  }

  function show(node) {
    if (node) {
      node.hidden = false;
    }
  }

  function hide(node) {
    if (node) {
      node.hidden = true;
    }
  }

  /* The two overflow hints (Layer 14 section 7.2). Each is static text that
   * lives beside its wrapper in the markup and is shown only while that wrapper
   * actually overflows -- so a person who cannot see the scrollbar is told the
   * content continues, and nobody is told so when it does not.
   *
   * `scrollWidth` and `clientWidth` are the browser's own measurements of its
   * own layout, not transported values, so comparing them is not a
   * recalculation of anything the server sent. No value from the response is
   * read here at all. */
  function applyScrollHint(wrapper, hint) {
    if (!wrapper || !hint) {
      return;
    }
    hint.hidden = !(wrapper.scrollWidth > wrapper.clientWidth);
  }

  function refreshScrollHints(view) {
    if (!view || view.suspendHints) {
      return;
    }
    applyScrollHint(view.chartWrapper, view.chartHint);
    applyScrollHint(view.southWrapper, view.southHint);
    applyScrollHint(view.tableWrapper, view.tableHint);
    applyScrollHint(view.transitWrapper, view.transitHint);
  }

  /* One measurement for a whole bulk expansion instead of one per row: reading
   * the geometry inside the loop would force a layout for each of up to 819
   * rows and measure states nobody ever saw. */
  function withoutHintUpdates(view, action) {
    view.suspendHints = true;
    try {
      action();
    } finally {
      view.suspendHints = false;
    }
    refreshScrollHints(view);
  }

  function detailRow(list, key, value) {
    list.appendChild(element("dt", "v-detail-key", key));
    list.appendChild(element("dd", "v-detail-value", value));
  }

  /* --- the inline note and the placeholder (Layer 15 section 2) -------- */

  function fillDefaultPlaceText() {
    var label = defaultPlaceLabel || "the configured default birthplace";
    setText(
      formNote,
      "Date is required. Leave the time blank to assume 12:00 noon. Leave " +
        `the birthplace blank to assume ${label}; its time zone applies. A ` +
        "supplied time is read in the birthplace's time zone."
    );
    placeField.placeholder = `${label} assumed if blank`;
  }

  /* --- the birthplace combobox (Layer 15 section 5.2) ------------------ */

  function optionId(position) {
    return `place-option-${String(position)}`;
  }

  function closeList() {
    clear(placeListbox);
    placeOptions = [];
    placeActive = -1;
    placeField.setAttribute("aria-expanded", "false");
    placeField.removeAttribute("aria-activedescendant");
  }

  function highlight(position) {
    var nodes = placeListbox.children;
    for (var index = 0; index < nodes.length; index++) {
      if (index === position) {
        nodes[index].classList.add("v-option-active");
        nodes[index].setAttribute("aria-selected", "true");
      } else {
        nodes[index].classList.remove("v-option-active");
        nodes[index].setAttribute("aria-selected", "false");
      }
    }
    placeActive = position;
    if (position === -1) {
      placeField.removeAttribute("aria-activedescendant");
    } else {
      placeField.setAttribute("aria-activedescendant", optionId(position));
    }
  }

  function openList(suggestions) {
    clear(placeListbox);
    placeOptions = suggestions;
    placeActive = -1;
    placeField.removeAttribute("aria-activedescendant");
    suggestions.forEach(function (suggestion, position) {
      /* Section 5.1: the option reads as `display_label`, which the server
       * built -- the label plus "(matched: …)" when the name that matched is a
       * different name. Which names count as different is decided by Layer 2's
       * normalisation, and this page does not have a second opinion about it:
       * it shows one string and, on selection, sends the other one back. */
      var item = element("li", "v-option", suggestion.display_label);
      item.id = optionId(position);
      item.setAttribute("role", "option");
      item.setAttribute("aria-selected", "false");
      placeListbox.appendChild(item);
    });
    placeField.setAttribute(
      "aria-expanded",
      suggestions.length ? "true" : "false"
    );
  }

  /* Section 5.2, immediate invalidation: the sequence moves and the in-flight
   * request is aborted the moment the field changes, not when the next
   * debounced request starts. A response that was already on its way therefore
   * carries an obsolete number and is dropped -- it can never reopen a list the
   * person has already left behind. */
  function invalidateSuggestions() {
    placeSequence = placeSequence + 1;
    if (placeTimer !== null) {
      clearTimeout(placeTimer);
      placeTimer = null;
    }
    if (placeInFlight) {
      placeInFlight.abort();
      placeInFlight = null;
    }
  }

  function clearSelection() {
    placeIdField.value = "";
    hide(placeMarker);
  }

  function selectSuggestion(position) {
    var suggestion = placeOptions[position];
    if (!suggestion) {
      return;
    }
    /* The field gets **exactly** the server's label, never the display text
     * with its "(matched: …)" tail: the server compares the submitted text
     * against the label it built for that record (section 5.3). */
    placeField.value = suggestion.label;
    placeIdField.value = String(suggestion.geoname_id);
    show(placeMarker);
    invalidateSuggestions();
    closeList();
    setText(fieldMessages.place_text, "");
    refreshStale();
  }

  function applySuggestions(mine, answer) {
    if (mine !== placeSequence) {
      return;
    }
    if (!answer || answer.q !== placeField.value) {
      return;
    }
    var suggestions = answer.suggestions;
    if (!suggestions || !suggestions.length) {
      closeList();
      return;
    }
    openList(suggestions);
  }

  function requestSuggestions(text) {
    var mine = placeSequence;
    var controller = new AbortController();
    placeInFlight = controller;

    fetch("/api/places", {
      method: "POST",
      mode: "same-origin",
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "X-Viewer-Token": token
      },
      body: JSON.stringify({ q: text })
    })
      .then(function (response) {
        if (!response.ok) {
          return null;
        }
        return response.json().then(
          function (document_) {
            return document_;
          },
          function () {
            return null;
          }
        );
      })
      .then(function (answer) {
        if (placeInFlight === controller) {
          placeInFlight = null;
        }
        applySuggestions(mine, answer);
      })
      .catch(function () {
        if (placeInFlight === controller) {
          placeInFlight = null;
        }
        /* A suggestion that does not arrive is not an error the page reports:
         * the birthplace is optional, the list is an aid, and an aborted
         * request is the normal case here. */
      });
  }

  /* The raw-length rule of section 5.2: at least two code points before the
   * first comma. `Array.from` counts code points rather than UTF-16 units, so
   * one astral character counts as one. */
  function longEnough(text) {
    var prefix = text.split(",")[0];
    return Array.from(prefix).length >= SUGGEST_MINIMUM;
  }

  function onPlaceInput() {
    clearSelection();
    setText(fieldMessages.place_text, "");
    invalidateSuggestions();
    refreshStale();
    var text = placeField.value;
    if (!longEnough(text)) {
      closeList();
      return;
    }
    placeTimer = setTimeout(function () {
      placeTimer = null;
      requestSuggestions(text);
    }, SUGGEST_DELAY);
  }

  function onPlaceKeydown(event) {
    var key = event.key;
    var count = placeOptions.length;
    if (key === "ArrowDown" || key === "ArrowUp") {
      if (count === 0) {
        return;
      }
      /* Wrapping, without arithmetic on anything transported: the two ends are
       * named outright rather than computed from a modulus. */
      var next;
      if (key === "ArrowDown") {
        next = placeActive === count - 1 ? 0 : placeActive + 1;
      } else {
        next = placeActive <= 0 ? count - 1 : placeActive - 1;
      }
      highlight(next);
      event.preventDefault();
      return;
    }
    if (key === "Enter") {
      if (count === 0) {
        return;
      }
      /* An open list swallows Enter: with an option highlighted it selects,
       * with none it does nothing at all. Nothing is ever chosen for the
       * person (section 5.2). */
      event.preventDefault();
      if (placeActive !== -1) {
        selectSuggestion(placeActive);
      }
      return;
    }
    if (key === "Escape") {
      if (count !== 0) {
        event.preventDefault();
      }
      closeList();
      return;
    }
    if (key === "Tab") {
      closeList();
    }
  }

  /* Section 2 rule 3: leaving a typed birthplace behind without choosing a
   * suggestion is what the prompt is for. The one blur it stays quiet on is the
   * one a *pointer press on an action button* causes: writing two or three
   * lines of prompt into the form between that button's `mousedown` and its
   * `mouseup` moves the button out from under the pointer, and the press is
   * swallowed by the layout change. The submission itself then shows the same
   * sentence, blocks and focuses this field (`firstProblem`), so nothing is
   * lost by waiting those few milliseconds. A keyboard Tab onto the same
   * button is not a press and shows the prompt at once. */
  function onPlaceBlur() {
    closeList();
    if (pointerOnAction) {
      return;
    }
    if (placeField.value.trim() !== "" && placeIdField.value === "") {
      setText(fieldMessages.place_text, SELECTION_PROMPT);
    }
  }

  function wireCombobox() {
    [generateButton, cancelButton].forEach(function (button) {
      button.addEventListener("mousedown", function () {
        pointerOnAction = true;
      });
    });
    window.addEventListener("mouseup", function () {
      pointerOnAction = false;
    });

    placeField.addEventListener("input", onPlaceInput);
    placeField.addEventListener("keydown", onPlaceKeydown);
    placeField.addEventListener("blur", onPlaceBlur);

    /* The pointer path. `mousedown` is prevented so that the field keeps focus
     * -- otherwise the blur handler would close the list under the click. */
    placeListbox.addEventListener("mousedown", function (event) {
      event.preventDefault();
    });
    placeListbox.addEventListener("click", function (event) {
      var item = event.target.closest ? event.target.closest(".v-option") : null;
      if (!item || !placeListbox.contains(item)) {
        return;
      }
      var position = -1;
      var nodes = placeListbox.children;
      for (var index = 0; index < nodes.length; index++) {
        if (nodes[index] === item) {
          position = index;
        }
      }
      if (position !== -1) {
        selectSuggestion(position);
      }
    });
  }

  /* --- form reading and syntax validation ---------------------------- */

  function currentValues() {
    return {
      date: dateField.value,
      time: timeField.value,
      place_text: placeField.value,
      place_id: placeIdField.value
    };
  }

  function clearFieldMessages() {
    setText(fieldMessages.date, "");
    setText(fieldMessages.time, "");
    setText(fieldMessages.place_text, "");
  }

  /* Syntax only, and no calendar knowledge: an impossible but well-formed
   * date such as 1995-02-30 is the server's to refuse (Layer 14 section 5),
   * because Layer 1 is the authority on what a date is. A blank time and a
   * blank birthplace are not problems at all -- they are the two assumptions
   * of Layer 15 section 2. */
  function firstProblem(values) {
    if (!DATE_SYNTAX.test(values.date)) {
      return {
        field: dateField,
        key: "date",
        message: "Enter the date as YYYY-MM-DD."
      };
    }
    if (values.time !== "" && !TIME_SYNTAX.test(values.time)) {
      return {
        field: timeField,
        key: "time",
        message:
          "Enter the local wall time as HH:MM or HH:MM:SS, or leave it blank."
      };
    }
    if (values.place_text.trim() !== "" && values.place_id === "") {
      return {
        field: placeField,
        key: "place_text",
        message: SELECTION_PROMPT
      };
    }
    return null;
  }

  /* --- status, alerts and the loading state -------------------------- */

  function announce(text) {
    setText(statusRegion, text);
  }

  function clearAlert() {
    clear(alertRegion);
    hide(alertRegion);
  }

  function showAlert(kind, message, hint) {
    clear(alertRegion);
    var title = ERROR_TITLES[kind];
    alertRegion.appendChild(
      element("p", "v-alert-title", title ? title : "The request failed")
    );
    alertRegion.appendChild(element("p", "v-alert-message", message));
    if (hint) {
      alertRegion.appendChild(element("p", "v-alert-message", hint));
    }
    show(alertRegion);
  }

  function enterLoading(superseded) {
    clearAlert();
    show(cancelButton);
    /* Generate deliberately stays enabled: pressing it again is how a request
     * is superseded (Layer 14 section 10.1). */
    resultsRegion.setAttribute("aria-busy", "true");
    resultsRegion.setAttribute("data-busy", "true");
    resultsRegion.setAttribute("inert", "");
    announce(
      superseded ? "Calculating… (previous request replaced)" : "Calculating…"
    );
    /* Layer 20 section 6.4: a natal request disowns any transit request. */
    natalLoading = true;
    if (invalidatePending() && transitOn) {
      setTransitStatus(
        "Transit request cancelled: the natal chart is being recalculated.",
        false
      );
    }
    syncOverlay();
  }

  function leaveLoading() {
    hide(cancelButton);
    resultsRegion.removeAttribute("aria-busy");
    resultsRegion.removeAttribute("data-busy");
    resultsRegion.removeAttribute("inert");
    /* Layer 20 section 6.4: a failed or cancelled natal request leaves
     * `shown` as it was, and the stale rule decides what is visible. */
    natalLoading = false;
    if (transitOn && overlayMeta === META_OK) {
      setTransitStatus(restingStatus(false), false);
    }
    syncOverlay();
  }

  /* --- the request --------------------------------------------------- */

  function submit() {
    clearFieldMessages();
    var values = currentValues();
    var problem = firstProblem(values);
    if (problem) {
      setText(fieldMessages[problem.key], problem.message);
      if (problem.field) {
        problem.field.focus();
      }
      announce("Nothing sent: the form is incomplete.");
      return;
    }

    sequence = sequence + 1;
    var mine = sequence;
    var captured = {
      date: values.date,
      time: values.time,
      place_text: values.place_text,
      place_id: values.place_id
    };

    var superseded = false;
    if (inFlight) {
      superseded = true;
      inFlight.abort();
    }
    var controller = new AbortController();
    inFlight = controller;

    enterLoading(superseded);

    fetch("/api/chart", {
      method: "POST",
      mode: "same-origin",
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "X-Viewer-Token": token
      },
      body: JSON.stringify(captured)
    })
      .then(function (response) {
        return response.json().then(
          function (document_) {
            return { status: response.status, ok: response.ok, body: document_ };
          },
          function () {
            return { status: response.status, ok: false, body: null };
          }
        );
      })
      .then(function (answer) {
        settle(mine, controller);
        if (mine !== sequence) {
          return;
        }
        leaveLoading();
        if (answer.body === null) {
          showAlert(
            "unexpected",
            "The server's answer was not the JSON document this page expects."
          );
          alertRegion.focus();
          announce("The request failed.");
          return;
        }
        if (!answer.ok) {
          applyError(answer.body);
          return;
        }
        if (!echoMatches(answer.body, captured)) {
          showAlert(
            "unexpected",
            "The server echoed a different submission than the one this page " +
              "sent. Nothing was applied."
          );
          alertRegion.focus();
          announce("The request failed.");
          return;
        }
        applyDocument(answer.body);
      })
      .catch(function (error) {
        settle(mine, controller);
        if (mine !== sequence) {
          return;
        }
        leaveLoading();
        if (error && error.name === "AbortError") {
          if (mine === cancelledSequence) {
            announce("Cancelled");
            generateButton.focus();
          }
          return;
        }
        showAlert(
          "unexpected",
          `The viewer could not reach its own server: ${String(error)}`
        );
        alertRegion.focus();
        announce("The request failed.");
      });
  }

  function settle(mine, controller) {
    if (inFlight === controller) {
      inFlight = null;
    }
  }

  /* Layer 14 section 10.2, over Layer 15's four strings: a response is applied
   * only if its echoed submission equals, string for string, the values
   * captured at that submission. This cannot fail against this server; it
   * guards against a different server answering on the port. */
  function echoMatches(document_, captured) {
    var echo =
      document_ && document_.request ? document_.request.submitted : null;
    if (!echo) {
      return false;
    }
    return (
      echo.date === captured.date &&
      echo.time === captured.time &&
      echo.place_text === captured.place_text &&
      echo.place_id === captured.place_id
    );
  }

  function applyError(document_) {
    var error = document_ && document_.error ? document_.error : null;
    var kind = error && error.kind ? error.kind : "unexpected";
    var message = error && error.message ? error.message : "No message.";

    if (kind === "stale_schema") {
      showAlert(kind, STALE_SCHEMA_SENTENCE, STALE_SCHEMA_HINT);
      announce(STALE_SCHEMA_SENTENCE);
      alertRegion.focus();
      return;
    }

    showAlert(kind, message);
    announce("The request failed.");

    if (kind === "place_selection_required") {
      setText(fieldMessages.place_text, SELECTION_PROMPT);
      placeField.focus();
      return;
    }
    if (kind === "place_not_found") {
      placeField.focus();
      return;
    }
    if (kind === "input") {
      focusNamedField(message);
      return;
    }
    if (kind === "dasha_range") {
      dateField.focus();
      return;
    }
    alertRegion.focus();
  }

  /* Layer 15 section 8: the field named in the message, when one is
   * identifiable, and the date otherwise. The `kind` decided that this is an
   * input error; the text decides only where the cursor goes. */
  function focusNamedField(message) {
    if (PLACE_WORDS.test(message)) {
      placeField.focus();
      return;
    }
    if (TIME_WORDS.test(message)) {
      timeField.focus();
      return;
    }
    dateField.focus();
  }

  /* --- applying one document ----------------------------------------- */

  function applyDocument(document_) {
    var fragment = resultsTemplate.content.cloneNode(true);
    var view = buildView(fragment, document_);

    /* One subtree swap (Layer 14 section 10.1): the finished results are built
     * off the document and put in place in a single operation, so the page
     * never shows a half-populated result. */
    var fresh = element("div", "v-results-body");
    fresh.id = "results-body";
    fresh.appendChild(fragment);
    resultsBody.parentNode.replaceChild(fresh, resultsBody);
    resultsBody = fresh;
    show(resultsRegion);
    clearAlert();

    shown = { document: document_, view: view };
    /* Layer 19 section 6.2: the persisted preference is applied to the new
     * subtree. `applyStyle` ends by measuring the scroll hints, now that the
     * subtree is in the document: geometry read off an off-document fragment
     * is meaningless. */
    applyStyle(view);
    refreshStale();
    /* Layer 20 section 6.4: the transit state belonged to the previous natal
     * object; its groups left with the replaced subtree. */
    onNatalApplied(document_);
    syncOverlay();

    announce(
      `Chart and daśā for ${document_.effective.place.label}, ` +
        `${document_.timeline.year_convention.display}`
    );
    if (view.heading) {
      view.heading.focus();
    }
  }

  function buildView(fragment, document_) {
    var view = {
      heading: fragment.querySelector("#results-heading"),
      stale: fragment.querySelector("#stale-banner"),
      body: fragment.querySelector("#dasha-body"),
      chartWrapper: fragment.querySelector("#chart-wrapper"),
      chartHint: fragment.querySelector("#chart-scroll-hint"),
      northBlock: fragment.querySelector("#chart-block-north"),
      southBlock: fragment.querySelector("#chart-block-south"),
      southWrapper: fragment.querySelector("#chart-south-wrapper"),
      southHint: fragment.querySelector("#chart-south-scroll-hint"),
      southMessage: fragment.querySelector("#chart-south-message"),
      southState: SOUTH_MISSING,
      tableWrapper: fragment.querySelector("#table-wrapper"),
      tableHint: fragment.querySelector("#table-scroll-hint"),
      northRoot: null,
      southRoot: null,
      transitPanel: fragment.querySelector("#transit-panel"),
      transitSummary: fragment.querySelector("#transit-summary"),
      transitAssumed: fragment.querySelector("#transit-assumed"),
      transitBody: fragment.querySelector("#transit-panel-body"),
      transitWrapper: fragment.querySelector("#transit-panel-wrapper"),
      transitHint: fragment.querySelector("#transit-panel-scroll-hint"),
      chartHeading: fragment.querySelector("#chart-heading"),
      southHeading: fragment.querySelector("#chart-south-heading"),
      nodesByRow: new Map(),
      idByChain: new Map(),
      abbrByLord: new Map(),
      microseconds: false,
      suspendHints: false
    };

    fillSummary(fragment, document_);
    fillBadges(fragment, document_);
    fillBirthDetails(fragment, document_);
    fillPanchanga(fragment, document_);
    fillChart(fragment, document_);
    view.southState = fillSouthChart(fragment, document_);
    /* Layer 20 section 6.5: the two roots a transit group is appended to. */
    view.northRoot = fragment.querySelector("#chart > svg");
    view.southRoot =
      view.southState === SOUTH_PRESENT
        ? fragment.querySelector("#chart-south > svg")
        : null;
    if (view.transitAssumed) {
      view.transitAssumed.hidden = !document_.assumptions.any;
    }
    fillBirthChain(fragment, document_);
    fillCaption(fragment, document_);
    fillTable(fragment, document_, view);
    wireControls(fragment, document_, view);
    return view;
  }

  /* Layer 15 section 3: an assumed value is never shown in the same form as a
   * supplied one, so the word travels with it everywhere. */
  function assumedPrefix(assumed) {
    return assumed ? "assumed " : "";
  }

  /* Panchanga is formatted by Python. No date parsing, rounding, astronomy
   * or day membership is performed here; the natal document owns this panel. */
  function panchangaTable(headers, rows) {
    var wrapper = element("div", "v-panchanga-table-wrapper");
    wrapper.tabIndex = 0;
    wrapper.setAttribute("role", "region");
    wrapper.setAttribute("aria-label", "Panchanga table; scroll horizontally if needed");
    var table = element("table", "v-panchanga-table");
    var head = element("thead", "v-panchanga-thead");
    var heading = element("tr", "v-panchanga-tr");
    headers.forEach(function (text) {
      var cell = element("th", "v-panchanga-th", text);
      cell.scope = "col";
      heading.appendChild(cell);
    });
    head.appendChild(heading);
    table.appendChild(head);
    var body = element("tbody", "v-panchanga-tbody");
    rows.forEach(function (values) {
      var row = element("tr", "v-panchanga-tr");
      values.forEach(function (text) {
        row.appendChild(element("td", "v-panchanga-td", text));
      });
      body.appendChild(row);
    });
    table.appendChild(body);
    wrapper.appendChild(table);
    return wrapper;
  }

  function panchangaValue(value) {
    return value.detail ? `${value.name} — ${value.detail}` : value.name;
  }

  function panchangaChanges(parent, title, changes) {
    if (!changes.length) { return; }
    parent.appendChild(element("h4", "v-panchanga-heading", title));
    parent.appendChild(panchangaTable(
      ["Element", "Change", "Local time (approx.)", "Boundary note"],
      changes.map(function (change) {
        return [change.kind, `${panchangaValue(change.before)} → ${panchangaValue(change.after)}`,
          change.after_time.display, change.placement_label];
      })
    ));
  }

  function fillPanchanga(fragment, document_) {
    var target = fragment.querySelector("#panchanga-body");
    var data = document_.panchanga;
    if (document_.assumptions.any) {
      var badge = fragment.querySelector("#panchanga-badge");
      setText(badge, "Uses assumed birth details");
      show(badge);
    }
    if (!data || data.schema !== "vedic_chart.panchanga/1") {
      target.appendChild(element("p", "v-note",
        "Panchanga is not included in this response. Generate a chart with the updated server."));
      return;
    }
    var content = document.createDocumentFragment();
    try {
      content.appendChild(element("p", "v-panchanga-context",
        `At the selected chart time: ${data.instant.display} (${data.timezone_id}), ` +
        `${document_.effective.place.label}.`));
      if (data.status !== "available") {
        content.appendChild(element("p", "v-notice", `Panchanga unavailable: ${data.reason}`));
      } else {
        var rows = [["Vara", data.vara ? `${data.vara.name} (${data.vara.weekday})` : "Unavailable",
          data.sunrise.status === "available" ? data.sunrise.next.display : "Sunrise unavailable"]];
        data.elements.forEach(function (item) {
          rows.push([item.label, panchangaValue(item.value), item.next.after_time.display]);
        });
        content.appendChild(panchangaTable(["Element", "At chart time", "Next change (approx.)"], rows));
        content.appendChild(element("p", "v-note", data.timing_note));
        content.appendChild(element("p", "v-note", data.sunrise_note));
        if (data.sunrise.status === "available") {
          content.appendChild(element("p", "v-panchanga-sunrise",
            `Sunrise window at chart time: ${data.sunrise.previous.display} → ${data.sunrise.next.display}`));
        } else {
          content.appendChild(element("p", "v-notice", data.sunrise.reason));
        }
        var day = data.day;
        var daily = element("details", "v-panchanga-details");
        daily.id = "panchanga-day";
        daily.appendChild(element("summary", "v-panchanga-summary", "Sunrise-to-sunrise day containing this instant"));
        if (day.status === "available") {
          daily.appendChild(element("p", "v-panchanga-context",
            `${day.civil_date} · ${day.vara} · sunrise ${day.sunrise_ordinal}`));
          daily.appendChild(element("p", "v-panchanga-sunrise",
            `${day.opening.display} → ${day.closing.display} (${data.timezone_id})`));
          daily.appendChild(element("p", "v-note", day.note));
          daily.appendChild(panchangaTable(["Element", "At opening sunrise"],
            day.at_opening.map(function (item) { return [item.label, panchangaValue(item.value)]; })));
          panchangaChanges(daily, "Changes listed for this sunrise day", day.transitions);
          panchangaChanges(daily, "Changes whose windows touch the closing sunrise", day.cells_at_closing);
          if (day.unordered_pairs.length) {
            daily.appendChild(element("p", "v-notice",
              "Some changes share a calculation window; their true order is not established."));
          }
        } else {
          daily.appendChild(element("p", "v-notice", `Daily Panchanga unavailable: ${day.reason}`));
          if (day.note) { daily.appendChild(element("p", "v-note", day.note)); }
        }
        content.appendChild(daily);
        var exact = element("details", "v-panchanga-details");
        exact.id = "panchanga-exact";
        exact.appendChild(element("summary", "v-panchanga-summary", "Exact calculation windows and conventions"));
        var windows = data.elements.map(function (item) {
          return [item.label, "Previous", item.previous.window];
        });
        data.elements.forEach(function (item) { windows.push([item.label, "Next", item.next.window]); });
        if (day.status === "available") {
          day.transitions.concat(day.cells_at_closing).forEach(function (change) {
            windows.push([change.kind, change.placement_label, change.window]);
          });
          exact.appendChild(element("p", "v-note", `Canonical sunrise boundaries: ${day.opening.local} → ${day.closing.local}`));
        }
        exact.appendChild(panchangaTable(["Element", "Boundary", "Local window (before, after]"], windows));
        exact.appendChild(element("p", "v-note", data.elements[0].next.ut1_note));
        exact.appendChild(element("p", "v-note", data.elements[0].next.model_note));
        exact.appendChild(element("p", "v-note", data.sunrise_convention));
        content.appendChild(exact);
      }
      target.appendChild(content);
    } catch (error) {
      target.appendChild(element("p", "v-notice", "Panchanga could not be displayed from this response. The chart remains available."));
    }
  }

  function fillSummary(fragment, document_) {
    var effective = document_.effective;
    setText(
      fragment.querySelector("#submitted-line"),
      `Computed from ${effective.date}, ` +
        `${assumedPrefix(effective.time_assumed)}${effective.time}, ` +
        `${assumedPrefix(effective.place_assumed)}${effective.place.label}`
    );

    var engine = document_.engine;
    var house = HOUSE_LABELS[engine.house_system];
    var node = NODE_LABELS[engine.node];
    var houseText = house ? `${house} houses` : engine.house_system;
    var nodeText = node ? node : engine.node;
    setText(
      fragment.querySelector("#engine-line"),
      `Ayanāṃśa: ${engine.ayanamsha} · ${houseText} · ${nodeText} · ` +
        `${engine.engine_spec}`
    );
    setText(fragment.querySelector("#validation-note"), engine.validation_note);

    setText(
      fragment.querySelector("#dasha-year"),
      ` — ${document_.timeline.year_convention.display}`
    );
  }

  function fillBadges(fragment, document_) {
    var any = document_.assumptions.any;
    /* Layer 19 section 6.5: the South Indian chart's badge mirrors the North
     * Indian one, so an assumed value is flagged on whichever chart is shown. */
    [
      "#results-badge",
      "#chart-badge",
      "#chart-south-badge",
      "#dasha-badge"
    ].forEach(function (id) {
      var badge = fragment.querySelector(id);
      if (!badge) {
        return;
      }
      if (any) {
        setText(badge, ASSUMED_BADGE);
        show(badge);
      } else {
        setText(badge, "");
        hide(badge);
      }
    });

    var list = fragment.querySelector("#assumption-labels");
    clear(list);
    document_.assumptions.labels.forEach(function (label) {
      list.appendChild(element("li", "v-assumption", label));
    });
  }

  /* The hemisphere words are chosen from the sign character of the string the
   * server sent, never from a number: no conversion, no comparison. */
  function hemisphere(text, positive, negative) {
    return text.charAt(0) === "-" ? negative : positive;
  }

  /* Layer 15 section 3: "Birth details" replaces Layer 14's "Resolved place".
   * Nothing was resolved on this path, so there is no dominance notice and no
   * candidate list; what there is instead is a source for every value. */
  function fillBirthDetails(fragment, document_) {
    var list = fragment.querySelector("#birth-details");
    var location = document_.location;
    var effective = document_.effective;
    var place = effective.place;

    detailRow(list, "Date", `${effective.date} (supplied)`);
    detailRow(
      list,
      "Time",
      effective.time_assumed
        ? `${effective.time} (assumed — no time was supplied)`
        : `${effective.time} (supplied)`
    );
    detailRow(
      list,
      "Birthplace",
      effective.place_assumed
        ? `${place.label} (assumed — the configured default; no birthplace ` +
            "was supplied)"
        : `${place.label} (supplied — selected from the list)`
    );
    detailRow(
      list,
      "Latitude",
      `${location.latitude} (${hemisphere(location.latitude, "N", "S")})`
    );
    detailRow(
      list,
      "Longitude",
      `${location.longitude} (${hemisphere(location.longitude, "E", "W")})`
    );
    detailRow(list, "Time zone", location.timezone_id);
    detailRow(
      list,
      "UTC offset at birth",
      `${document_.birth.offset} (${document_.birth.zone})`
    );
    detailRow(list, "Birth, local", document_.birth.local_seconds);
    detailRow(list, "Birth, UTC", document_.birth.utc);
    detailRow(list, "GeoNames id", String(place.geoname_id));
    detailRow(
      list,
      "Feature code",
      place.feature_code === null ? "unrecorded" : place.feature_code
    );
    detailRow(list, "Population", String(place.population));
  }

  function fillChart(fragment, document_) {
    var container = fragment.querySelector("#chart");
    var message = fragment.querySelector("#chart-message");
    var accepted = insertSvg(container, document_.svg);
    if (accepted) {
      hide(message);
    } else {
      setText(
        message,
        "The chart could not be shown: the server's SVG was not the document " +
          "this page accepts."
      );
      show(message);
    }
  }

  /* Layer 19 section 6.4: the South Indian document, through the very same
   * `insertSvg` as the North Indian one, on every applied document whatever
   * the selected style. The returned state is the `southState` of section 5.6:
   * `missing` when the key is absent or not a string (an older server),
   * `rejected` when `insertSvg` refused it, `present` when it was inserted. The
   * notice is written here and shown or hidden by `applyStyle`. */
  function fillSouthChart(fragment, document_) {
    var container = fragment.querySelector("#chart-south");
    var message = fragment.querySelector("#chart-south-message");
    var text = document_.south_indian_svg;
    if (typeof text !== "string") {
      clear(container);
      setText(message, SOUTH_MISSING_NOTICE);
      return SOUTH_MISSING;
    }
    if (insertSvg(container, text)) {
      setText(message, "");
      return SOUTH_PRESENT;
    }
    clear(container);
    setText(message, SOUTH_REJECTED_NOTICE);
    return SOUTH_REJECTED;
  }

  /* Layer 19 sections 5.6 and 6.3 to 6.5: the selected style applied to one
   * shown document, and nothing else. The North Indian block is hidden only
   * when South Indian is selected **and** its document was inserted; the South
   * Indian block is visible whenever South Indian or Both is selected, showing
   * either its chart or its notice and an empty container. No request, no
   * parse, no form field and no stale-input state is touched here. */
  function applyStyle(view) {
    if (!view || !view.northBlock || !view.southBlock) {
      return;
    }
    var southOk = view.southState === SOUTH_PRESENT;
    var hideNorth = chartStyle === STYLE_SOUTH && southOk;
    var showSouth = chartStyle === STYLE_SOUTH || chartStyle === STYLE_BOTH;

    var active = document.activeElement;
    var focusLost =
      active !== null &&
      ((hideNorth && !view.northBlock.hidden && view.northBlock.contains(active)) ||
        (!showSouth && !view.southBlock.hidden && view.southBlock.contains(active)));

    view.northBlock.hidden = hideNorth;
    view.southBlock.hidden = !showSouth;
    view.southWrapper.hidden = !southOk;
    view.southMessage.hidden = southOk;

    if (mainRegion) {
      if (chartStyle === STYLE_BOTH && shown !== null) {
        mainRegion.classList.add("v-main-wide");
      } else {
        mainRegion.classList.remove("v-main-wide");
      }
    }
    if (styleGroup) {
      styleGroup.disabled = false;
    }

    /* Section 6.5: focus stays where the browser keeps it, unless it was
     * inside the block just hidden; then it goes to the checked radio rather
     * than being lost to the body. */
    if (focusLost) {
      styleInputs.forEach(function (input) {
        if (input && input.checked) {
          input.focus();
        }
      });
    }
    refreshScrollHints(view);
  }

  function onStyleChange(event) {
    var input = event.target;
    if (!input || !input.checked) {
      return;
    }
    if (input.value === STYLE_SOUTH) {
      chartStyle = STYLE_SOUTH;
    } else if (input.value === STYLE_BOTH) {
      chartStyle = STYLE_BOTH;
    } else {
      chartStyle = STYLE_NORTH;
    }
    applyStyle(shown && shown.view);
    syncOverlay();
  }

  /* Section 6.1: North Indian is checked when the page starts, whatever state
   * the browser may have restored into the radios, and the group stays
   * disabled until the first document is shown. */
  function wireStyleControl() {
    styleInputs.forEach(function (input) {
      if (!input) {
        return;
      }
      input.checked = input.value === STYLE_NORTH;
      input.addEventListener("change", onStyleChange);
    });
    chartStyle = STYLE_NORTH;
    if (styleGroup) {
      styleGroup.disabled = true;
    }
  }

  /* Layer 14 section 7.3. The string is parsed as image/svg+xml and accepted
   * only if the document element is `svg` in the SVG namespace and the tree
   * carries no `script`, no `foreignObject` and no `on*` attribute -- a
   * defensive check on our own renderer's output, which never has any. The
   * element is then adopted into the emptied container, so the `d1-*` ids stay
   * unique. */
  function insertSvg(container, text) {
    if (typeof text !== "string" || text === "") {
      return false;
    }
    var parsed = new DOMParser().parseFromString(text, "image/svg+xml");
    if (parsed.getElementsByTagName("parsererror").length > 0) {
      return false;
    }
    var root = parsed.documentElement;
    if (!root || root.namespaceURI !== SVG_NAMESPACE || root.localName !== "svg") {
      return false;
    }
    if (root.getElementsByTagName("script").length > 0) {
      return false;
    }
    if (root.getElementsByTagName("foreignObject").length > 0) {
      return false;
    }
    var nodes = [root].concat(Array.prototype.slice.call(root.getElementsByTagName("*")));
    for (var index = 0; index < nodes.length; index++) {
      var attributes = nodes[index].attributes;
      for (var position = 0; position < attributes.length; position++) {
        if (EVENT_HANDLER_ATTRIBUTE.test(attributes[position].name)) {
          return false;
        }
      }
    }

    clear(container);
    var adopted = document.adoptNode(root);
    /* Layer 14 section 7.2, applied as this one element's own style rather than
     * as a stylesheet rule, because no viewer CSS rule may select inside the
     * chart container. The renderer's viewBox preserves the aspect ratio at any
     * size; 600 px is its supported minimum, below which the wrapper scrolls. */
    adopted.style.display = "block";
    adopted.style.width = "100%";
    adopted.style.height = "auto";
    adopted.style.maxWidth = "1080px";
    adopted.style.minWidth = "600px";
    container.appendChild(adopted);
    return true;
  }

  function chainAbbr(lords, abbrByLord) {
    return lords
      .map(function (lord) {
        return abbrByLord.get(lord) || lord;
      })
      .join("-");
  }

  function fillBirthChain(fragment, document_) {
    var abbrByLord = new Map();
    document_.rows.forEach(function (row) {
      if (row.level === 1) {
        abbrByLord.set(row.lords[0], row.chain);
      }
    });

    var list = fragment.querySelector("#birth-chain-details");
    detailRow(
      list,
      "Nominal",
      document_.birth_chain.nominal
        .map(function (entry) {
          return chainAbbr(entry.lords, abbrByLord);
        })
        .join(CHAIN_SEPARATOR)
    );
    detailRow(
      list,
      "Quantized",
      document_.birth_chain.quantized
        .map(function (entry) {
          return chainAbbr(entry.lords, abbrByLord);
        })
        .join(CHAIN_SEPARATOR)
    );

    var note = fragment.querySelector("#divergence-note");
    if (document_.birth_chain.identical) {
      hide(note);
    } else {
      setText(note, DIVERGENCE_NOTE);
      show(note);
    }
  }

  function fillCaption(fragment, document_) {
    var caption = fragment.querySelector("#table-caption");
    var timeline = document_.timeline;
    clear(caption);

    var nakshatraNumber = String(timeline.nakshatra_number);
    caption.appendChild(
      element(
        "p",
        "v-caption-line",
        `Moon ${timeline.moon_sidereal_longitude} ` +
          `(${timeline.nakshatra_name} #${nakshatraNumber}), ` +
          `lord ${timeline.lord.name}`
      )
    );
    caption.appendChild(
      element(
        "p",
        "v-caption-line",
        "Nominal balance of the first Mahadasha at birth: " +
          `${timeline.balance_years.num}/${timeline.balance_years.den} = ` +
          `${timeline.balance_years.decimal_9} years ` +
          "(nominal; decimal truncated to 9 places)"
      )
    );
    /* Layer 15 section 6: the sentence is Python's, not this page's. */
    caption.appendChild(
      element(
        "p",
        "v-caption-line",
        `${timeline.year_convention.display} · shown in ${timeline.zone}`
      )
    );
    caption.appendChild(element("p", "v-caption-line", HALF_OPEN_NOTE));
    caption.appendChild(element("p", "v-caption-line", PRE_BIRTH_NOTE));
  }

  /* --- the treegrid --------------------------------------------------- */

  /* Layer 14 section 9.3: a level-k row belongs to the most recent level-(k-1)
   * row. A structural rule over the array the server sent, not a comparison of
   * any transported value. */
  function buildTree(rows) {
    var roots = [];
    var stack = [];
    rows.forEach(function (row) {
      var node = { row: row, children: [] };
      while (stack.length >= row.level) {
        stack.pop();
      }
      if (stack.length === 0) {
        roots.push(node);
      } else {
        stack[stack.length - 1].children.push(node);
      }
      stack.push(node);
    });
    return roots;
  }

  function rowId(chain) {
    return `row-${chain.toLowerCase()}`;
  }

  function instantText(instant, microseconds) {
    return microseconds ? instant.local : instant.local_seconds;
  }

  function rowLabel(row, microseconds) {
    var parts = [
      `${LEVEL_WORD[row.level]} ${row.chain_names}`,
      `${instantText(row.start, microseconds)} to ` +
        `${instantText(row.end, microseconds)}`
    ];
    if (row.in_nominal_birth_chain) {
      parts.push("N");
    }
    if (row.in_quantized_birth_chain) {
      parts.push("Q");
    }
    return parts.join(", ");
  }

  function makeRow(node, view) {
    var row = node.row;
    var tr = element("tr", `v-row v-level-${String(row.level)}`);
    tr.setAttribute("role", "row");
    tr.id = rowId(row.chain);
    tr.setAttribute("aria-level", String(row.level));
    tr.setAttribute("aria-posinset", String(row.posinset));
    tr.setAttribute("aria-setsize", SET_SIZE);
    tr.tabIndex = -1;
    if (row.in_nominal_birth_chain) {
      tr.classList.add("v-birth-nominal");
    }
    if (row.in_quantized_birth_chain) {
      tr.classList.add("v-birth-quantized");
    }

    var expandable = node.children.length > 0;
    if (expandable) {
      tr.classList.add("v-expandable");
      tr.setAttribute("aria-expanded", "false");
    }

    var level = element("td", "v-cell v-cell-level");
    var toggle = element("span", "v-toggle", expandable ? "▸" : "");
    toggle.setAttribute("aria-hidden", "true");
    level.appendChild(toggle);
    level.appendChild(document.createTextNode(LEVEL_ABBR[row.level]));
    tr.appendChild(level);

    var chain = element("td", "v-cell v-cell-chain", row.chain);
    chain.title = row.chain_names;
    tr.appendChild(chain);

    tr.appendChild(
      element("td", "v-cell v-cell-start", instantText(row.start, view.microseconds))
    );
    tr.appendChild(
      element("td", "v-cell v-cell-end", instantText(row.end, view.microseconds))
    );
    tr.appendChild(
      element("td", "v-cell v-cell-marker", row.in_nominal_birth_chain ? "N" : "")
    );
    tr.appendChild(
      element("td", "v-cell v-cell-marker", row.in_quantized_birth_chain ? "Q" : "")
    );

    tr.setAttribute("aria-label", rowLabel(row, view.microseconds));
    view.nodesByRow.set(tr, node);
    return tr;
  }

  function updateToggle(tr, expanded) {
    var toggle = tr.querySelector(".v-toggle");
    if (toggle) {
      toggle.textContent = expanded ? "▾" : "▸";
    }
  }

  function isExpandable(tr) {
    return tr.hasAttribute("aria-expanded");
  }

  function isExpanded(tr) {
    return tr.getAttribute("aria-expanded") === "true";
  }

  function expandRow(tr, view) {
    if (!isExpandable(tr) || isExpanded(tr)) {
      return;
    }
    var node = view.nodesByRow.get(tr);
    var anchor = tr;
    node.children.forEach(function (child) {
      var childRow = makeRow(child, view);
      anchor.parentNode.insertBefore(childRow, anchor.nextSibling);
      anchor = childRow;
    });
    tr.setAttribute("aria-expanded", "true");
    updateToggle(tr, true);
    refreshScrollHints(view);
  }

  /* Decision D8: collapsing removes the descendants outright, so their own
   * expanded state is forgotten rather than remembered. If focus was on one of
   * them it moves to the row that was collapsed -- focus is never lost to the
   * body. */
  function collapseRow(tr, view) {
    if (!isExpandable(tr) || !isExpanded(tr)) {
      return;
    }
    var node = view.nodesByRow.get(tr);
    var doomed = [];
    var next = tr.nextElementSibling;
    while (next) {
      var nextNode = view.nodesByRow.get(next);
      if (!nextNode || nextNode.row.level <= node.row.level) {
        break;
      }
      doomed.push(next);
      next = next.nextElementSibling;
    }
    var hadFocus = false;
    doomed.forEach(function (victim) {
      if (victim === document.activeElement) {
        hadFocus = true;
      }
      view.nodesByRow.delete(victim);
      victim.parentNode.removeChild(victim);
    });
    tr.setAttribute("aria-expanded", "false");
    updateToggle(tr, false);
    refreshScrollHints(view);
    if (hadFocus) {
      focusRow(tr, view);
    }
  }

  function toggleRow(tr, view) {
    if (!isExpandable(tr)) {
      return;
    }
    if (isExpanded(tr)) {
      collapseRow(tr, view);
    } else {
      expandRow(tr, view);
    }
  }

  function focusRow(tr, view) {
    var rows = view.body.children;
    for (var index = 0; index < rows.length; index++) {
      rows[index].tabIndex = -1;
    }
    tr.tabIndex = 0;
    view.current = tr;
    tr.focus();
  }

  function parentRow(tr, view) {
    var node = view.nodesByRow.get(tr);
    var previous = tr.previousElementSibling;
    while (previous) {
      var candidate = view.nodesByRow.get(previous);
      if (candidate && candidate.row.level < node.row.level) {
        return previous;
      }
      previous = previous.previousElementSibling;
    }
    return null;
  }

  function ancestorMahadasha(tr, view) {
    var walk = tr;
    while (walk) {
      var node = view.nodesByRow.get(walk);
      if (node && node.row.level === 1) {
        return walk;
      }
      walk = walk.previousElementSibling;
    }
    return null;
  }

  function fillTable(fragment, document_, view) {
    var roots = buildTree(document_.rows);
    view.roots = roots;
    document_.rows.forEach(function (row) {
      if (row.level === 1) {
        view.abbrByLord.set(row.lords[0], row.chain);
      }
    });
    roots.forEach(function (node) {
      view.body.appendChild(makeRow(node, view));
    });
    if (view.body.firstElementChild) {
      view.body.firstElementChild.tabIndex = 0;
      view.current = view.body.firstElementChild;
    }

    view.body.addEventListener("click", function (event) {
      var tr = event.target.closest ? event.target.closest(".v-row") : null;
      if (!tr || !view.body.contains(tr)) {
        return;
      }
      focusRow(tr, view);
      var cell = event.target.closest(".v-cell-level");
      if (cell) {
        toggleRow(tr, view);
      }
    });

    view.body.addEventListener("keydown", function (event) {
      var tr = event.target.closest ? event.target.closest(".v-row") : null;
      if (!tr || !view.body.contains(tr)) {
        return;
      }
      handleKey(event, tr, view);
    });
  }

  function handleKey(event, tr, view) {
    var key = event.key;
    if (key === "ArrowDown") {
      var down = tr.nextElementSibling;
      if (down) {
        focusRow(down, view);
      }
      event.preventDefault();
      return;
    }
    if (key === "ArrowUp") {
      var up = tr.previousElementSibling;
      if (up) {
        focusRow(up, view);
      }
      event.preventDefault();
      return;
    }
    if (key === "ArrowRight") {
      if (isExpandable(tr)) {
        if (isExpanded(tr)) {
          var child = tr.nextElementSibling;
          if (child) {
            focusRow(child, view);
          }
        } else {
          expandRow(tr, view);
        }
      }
      event.preventDefault();
      return;
    }
    if (key === "ArrowLeft") {
      if (isExpandable(tr) && isExpanded(tr)) {
        collapseRow(tr, view);
      } else {
        var parent = parentRow(tr, view);
        if (parent) {
          focusRow(parent, view);
        }
      }
      event.preventDefault();
      return;
    }
    if (key === "Enter" || key === " " || key === "Spacebar") {
      toggleRow(tr, view);
      event.preventDefault();
      return;
    }
    if (key === "Home") {
      if (view.body.firstElementChild) {
        focusRow(view.body.firstElementChild, view);
      }
      event.preventDefault();
      return;
    }
    if (key === "End") {
      if (view.body.lastElementChild) {
        focusRow(view.body.lastElementChild, view);
      }
      event.preventDefault();
    }
  }

  function refreshInstants(view) {
    var rows = view.body.children;
    for (var index = 0; index < rows.length; index++) {
      var tr = rows[index];
      var node = view.nodesByRow.get(tr);
      if (!node) {
        continue;
      }
      var start = tr.querySelector(".v-cell-start");
      var end = tr.querySelector(".v-cell-end");
      setText(start, instantText(node.row.start, view.microseconds));
      setText(end, instantText(node.row.end, view.microseconds));
      tr.setAttribute("aria-label", rowLabel(node.row, view.microseconds));
    }
  }

  function wireControls(fragment, document_, view) {
    fragment
      .querySelector("#expand-all")
      .addEventListener("click", function () {
        /* Bounded by construction: the server sends at most 819 rows. */
        withoutHintUpdates(view, function () {
          var row = view.body.firstElementChild;
          while (row) {
            expandRow(row, view);
            row = row.nextElementSibling;
          }
        });
      });

    fragment
      .querySelector("#collapse-all")
      .addEventListener("click", function () {
        var target = view.current ? ancestorMahadasha(view.current, view) : null;
        withoutHintUpdates(view, function () {
          var row = view.body.firstElementChild;
          while (row) {
            var node = view.nodesByRow.get(row);
            if (node && node.row.level === 1) {
              collapseRow(row, view);
            }
            row = row.nextElementSibling;
          }
        });
        if (target && view.body.contains(target)) {
          focusRow(target, view);
        } else if (view.body.firstElementChild) {
          focusRow(view.body.firstElementChild, view);
        }
      });

    fragment
      .querySelector("#expand-birth")
      .addEventListener("click", function () {
        withoutHintUpdates(view, function () {
          expandChain(document_.birth_chain.nominal, view);
          if (!document_.birth_chain.identical) {
            expandChain(document_.birth_chain.quantized, view);
          }
        });
        var last = document_.birth_chain.nominal[2];
        var target = document.getElementById(
          rowId(chainAbbr(last.lords, view.abbrByLord))
        );
        if (target) {
          focusRow(target, view);
          target.scrollIntoView({ block: "center" });
        }
      });

    fragment
      .querySelector("#microseconds")
      .addEventListener("change", function (event) {
        view.microseconds = event.target.checked;
        refreshInstants(view);
        refreshScrollHints(view);
      });
  }

  /* It expands; it never collapses another row (Layer 14 section 8.2). */
  function expandChain(chain, view) {
    chain.forEach(function (entry) {
      var target = document.getElementById(
        rowId(chainAbbr(entry.lords, view.abbrByLord))
      );
      if (target && view.body.contains(target)) {
        expandRow(target, view);
      }
    });
  }

  /* --- the stale-inputs banner (Layer 14 section 10.3) ----------------- */

  /* Layer 15 section 3: the comparison is over the four submitted strings, so
   * clearing a field after a result marks the result stale exactly as editing
   * does -- a cleared birthplace is a different submission, not the same one. */
  function describeSubmitted(submitted) {
    var time = submitted.time === "" ? "no time supplied" : submitted.time;
    var place =
      submitted.place_text.trim() === ""
        ? "no birthplace supplied"
        : submitted.place_text;
    return `${submitted.date}, ${time}, ${place}`;
  }

  function refreshStale() {
    if (!shown) {
      return;
    }
    var submitted = shown.document.request.submitted;
    var values = currentValues();
    var same =
      values.date === submitted.date &&
      values.time === submitted.time &&
      values.place_text === submitted.place_text &&
      values.place_id === submitted.place_id;
    var wasStale = resultsRegion.hasAttribute("data-stale");
    if (same) {
      resultsRegion.removeAttribute("data-stale");
      hide(shown.view.stale);
      onNatalStale(wasStale, false);
      return;
    }
    resultsRegion.setAttribute("data-stale", "true");
    setText(
      shown.view.stale,
      `Inputs changed — the results below are for ` +
        `${describeSubmitted(submitted)}. Press Generate to recalculate.`
    );
    show(shown.view.stale);
    onNatalStale(wasStale, true);
  }

  /* --- Layer 20: the transit overlay ---------------------------------- */

  /* Section 6.6: the status line. Transit-initiated messages are mirrored to
   * the page's own live region; messages caused by the natal flow (a new
   * document, a natal edit) are written to #transit-status only, so that they
   * never replace the natal flow's own announcement in #status. */
  function setTransitStatus(text, mirror) {
    setText(transitStatus, text);
    if (mirror) {
      announce(text);
    }
  }

  function sameKey(a, b) {
    return a.natal === b.natal && a.date === b.date && a.time === b.time;
  }

  function currentKey() {
    return {
      natal: shown,
      date: transitDateField.value,
      time: transitTimeField.value
    };
  }

  function natalUsable() {
    return (
      shown !== null &&
      overlayMeta === META_OK &&
      !natalLoading &&
      !resultsRegion.hasAttribute("data-stale")
    );
  }

  /* THE predicate: every show and re-show, from any event, goes through it. */
  function overlayVisible() {
    return (
      transitOn &&
      natalUsable() &&
      transitResult !== null &&
      sameKey(transitResult.key, currentKey())
    );
  }

  /* Called at the end of every handler: shows or hides, never builds. */
  function syncOverlay() {
    if (overlayVisible()) {
      showOverlay(transitResult);
    } else {
      hideOverlay();
    }
  }

  function enterTransitBusy() {
    transitGroup.setAttribute("aria-busy", "true");
    setTransitStatus(CALCULATING_TRANSITS, true);
  }

  function leaveTransitBusy() {
    transitGroup.removeAttribute("aria-busy");
  }

  /* Ownership first, then the request itself. Returns whether a pending
   * request was disowned. */
  function invalidatePending() {
    var disowned = false;
    if (transitPending) {
      var pending = transitPending;
      transitPending = null;
      transitSequence = transitSequence + 1;
      pending.controller.abort();
      disowned = true;
    }
    leaveTransitBusy();
    return disowned;
  }

  function owns(mine) {
    return transitPending !== null && transitPending.sequence === mine;
  }

  function inputsComplete() {
    return (
      DATE_SYNTAX.test(transitDateField.value) &&
      TIME_SYNTAX.test(transitTimeField.value)
    );
  }

  function transitInstantText(meta) {
    return `${meta.date} ${meta.time} ${meta.zone} (UTC${meta.offset})`;
  }

  /* The status line when nothing is happening, for the toggle being on. */
  function restingStatus(fromTransitInput) {
    if (!natalUsable()) {
      return natalLoading
        ? "Transits wait for the natal chart to finish calculating."
        : NATAL_STALE_TRANSIT;
    }
    if (transitPending) {
      return CALCULATING_TRANSITS;
    }
    if (overlayVisible()) {
      return transitResult.statusText;
    }
    if (transitFailure !== null && sameKey(transitFailure.key, currentKey())) {
      return transitFailure.statusText;
    }
    if (!inputsComplete()) {
      return INCOMPLETE_TRANSIT;
    }
    var pair = `${transitDateField.value} ${transitTimeField.value}`;
    if (fromTransitInput || transitResult !== null) {
      return `Transit inputs changed — press Update to show transits for ${pair}.`;
    }
    return `Press Update to show transits for ${pair}.`;
  }

  /* --- section 6.7: validation, by string syntax and identity only ------ */

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isCoordinate(value) {
    return typeof value === "string" && COORDINATE_SYNTAX.test(value);
  }

  /* An integer count >= 0, checked on its decimal spelling: no conversion. */
  function isCount(value) {
    return typeof value === "number" && COUNT_SYNTAX.test(String(value));
  }

  function isSignValue(value) {
    return typeof value === "number" && SIGN_NUMBERS.indexOf(value) !== -1;
  }

  function exactSignKeys(map) {
    if (!isObject(map)) {
      return false;
    }
    var keys = Object.keys(map);
    if (keys.length !== SIGN_KEYS.length) {
      return false;
    }
    return SIGN_KEYS.every(function (key) {
      return Object.prototype.hasOwnProperty.call(map, key);
    });
  }

  function rungProblem(rung, layout, where) {
    if (!isObject(rung)) {
      return `${where} is not an object`;
    }
    if (!isCoordinate(rung.font_size) || !isCoordinate(rung.x)) {
      return `${where} has no usable font_size or x`;
    }
    if (layout === LAYOUT_INLINE) {
      if (!isCoordinate(rung.deg_x)) {
        return `${where} has no usable deg_x`;
      }
      if (!Array.isArray(rung.rows) || !rung.rows.every(isCoordinate)) {
        return `${where} has unusable rows`;
      }
      return null;
    }
    if (!Array.isArray(rung.entries)) {
      return `${where} has no entries`;
    }
    for (var index = 0; index < rung.entries.length; index++) {
      var entry = rung.entries[index];
      if (!isObject(entry) || !isCoordinate(entry.abbr_y) || !isCoordinate(entry.deg_y)) {
        return `${where} has an unusable entry`;
      }
    }
    if (rung.entries.length === 0) {
      return rung.overflow_y === null ? null : `${where} has an overflow row but no entry`;
    }
    return isCoordinate(rung.overflow_y) ? null : `${where} has no usable overflow_y`;
  }

  function slotProblem(slot, where) {
    if (!isObject(slot)) {
      return `${where} is not an object`;
    }
    if (!isSignValue(slot.house)) {
      return `${where} has no house 1 to 12`;
    }
    if (slot.layout !== LAYOUT_INLINE && slot.layout !== LAYOUT_STACKED) {
      return `${where} has an unknown layout`;
    }
    if (!isCount(slot.natal_rows)) {
      return `${where} has no natal_rows count`;
    }
    if (!Array.isArray(slot.rungs) || slot.rungs.length === 0) {
      return `${where} has no rungs`;
    }
    if (!isObject(slot.rungs[slot.rungs.length - 1]) ||
        slot.rungs[slot.rungs.length - 1].font_size !== FLOOR_FONT) {
      return `${where} does not end with the ${FLOOR_FONT} floor rung`;
    }
    for (var index = 0; index < slot.rungs.length; index++) {
      var problem = rungProblem(slot.rungs[index], slot.layout, `${where} rung ${String(index)}`);
      if (problem !== null) {
        return problem;
      }
    }
    var marker = slot.marker;
    if (marker !== null) {
      if (!isObject(marker) || !isCoordinate(marker.x) || !isCoordinate(marker.y) ||
          MARKER_ANCHORS.indexOf(marker.anchor) === -1) {
        return `${where} has an unusable marker`;
      }
    }
    return null;
  }

  /* The natal document's block, at applyDocument. Null when usable. */
  function natalOverlayProblem(document_) {
    var block = document_ ? document_.overlay : undefined;
    if (block === undefined) {
      return "no overlay block";
    }
    if (!isObject(block)) {
      return "the overlay block is not an object";
    }
    if (block.schema !== OVERLAY_SCHEMA) {
      return "unknown overlay schema";
    }
    if (typeof block.prefix !== "string" || block.prefix === "") {
      return "no prefix";
    }
    if (typeof block.font_family !== "string" || block.font_family === "") {
      return "no font_family";
    }
    if (!isCoordinate(block.marker_font_size)) {
      return "no marker_font_size";
    }
    if (!isObject(block.slots)) {
      return "no slots";
    }
    var styles = ["north", "south"];
    for (var position = 0; position < styles.length; position++) {
      var style = styles[position];
      if (!exactSignKeys(block.slots[style])) {
        return `slots.${style} does not hold exactly the signs 1 to 12`;
      }
      for (var index = 0; index < SIGN_KEYS.length; index++) {
        var sign = SIGN_KEYS[index];
        var problem = slotProblem(block.slots[style][sign], `slots.${style}.${sign}`);
        if (problem !== null) {
          return problem;
        }
      }
    }
    var seen = {};
    for (var at = 0; at < SIGN_KEYS.length; at++) {
      var key = SIGN_KEYS[at];
      var house = block.slots.north[key].house;
      if (house !== block.slots.south[key].house) {
        return `sign ${key} has different houses in the two styles`;
      }
      if (seen[String(house)]) {
        return "the houses are not a permutation of 1 to 12";
      }
      seen[String(house)] = true;
    }
    return null;
  }

  /* The transit document's entries and placements, at acceptance. */
  function transitOverlayProblem(document_, natalBlock) {
    var block = document_.overlay;
    var positions = document_.planetary_positions;
    if (!isObject(block) || block.schema !== OVERLAY_SCHEMA) {
      return "no overlay block of the known schema";
    }
    if (block.prefix !== natalBlock.prefix) {
      return "a different prefix";
    }
    if (!isObject(positions) || positions.schema !== POSITIONS_SCHEMA) {
      return "no planetary positions of the known schema";
    }
    var entries = block.entries;
    var planets = positions.planets;
    if (!Array.isArray(entries) || entries.length !== TRANSIT_COUNT) {
      return "not nine entries";
    }
    if (!Array.isArray(planets) || planets.length !== TRANSIT_COUNT) {
      return "not nine planets";
    }
    var keys = {};
    for (var index = 0; index < TRANSIT_COUNT; index++) {
      var entry = entries[index];
      var planet = planets[index];
      var where = `entry ${String(index)}`;
      if (!isObject(entry) || !isObject(planet) || !isObject(planet.sign)) {
        return `${where} is not an object`;
      }
      if (typeof entry.key !== "string" || entry.key !== planet.key) {
        return `${where} does not match the planet in the same position`;
      }
      if (keys[entry.key]) {
        return `${where} repeats the key ${entry.key}`;
      }
      keys[entry.key] = true;
      if (typeof entry.abbr !== "string" || entry.abbr.length !== 2) {
        return `${where} has no two-letter abbreviation`;
      }
      if (typeof entry.degree_text !== "string" || !DEGREE_TEXT_SYNTAX.test(entry.degree_text)) {
        return `${where} has no degree text`;
      }
      if (typeof entry.underline !== "boolean") {
        return `${where} has no underline flag`;
      }
      if (!isSignValue(planet.sign.number) || typeof planet.sign.name !== "string") {
        return `${where} has no sign 1 to 12`;
      }
      if (typeof planet.kind !== "string") {
        return `${where} has no kind`;
      }
      if (entry.rashi_number !== planet.sign.number) {
        return `${where} is not in its planet's sign`;
      }
    }
    return null;
  }

  /* --- section 6.5: composition in detached nodes ----------------------- */

  function svgElement(tag) {
    return document.createElementNS(SVG_NAMESPACE, tag);
  }

  function transitText(className, x, y, size, family, anchor, content) {
    var node = svgElement("text");
    node.setAttribute("class", className);
    node.setAttribute("x", x);
    node.setAttribute("y", y);
    node.setAttribute("font-size", size);
    node.setAttribute("font-family", family);
    node.setAttribute("fill", TRANSIT_FILL);
    node.setAttribute("text-anchor", anchor);
    node.textContent = content;
    return node;
  }

  function capacityOf(rung, layout) {
    return layout === LAYOUT_STACKED ? rung.entries.length : rung.rows.length;
  }

  /* One drawn entry: the prefixed abbreviation and its degree text, on one
   * baseline (inline) or on two rows (stacked). */
  function drawEntry(cell, rung, layout, row, entry, prefix, family) {
    var abbrY = layout === LAYOUT_STACKED ? rung.entries[row].abbr_y : rung.rows[row];
    var abbr = transitText(
      "transit", rung.x, abbrY, rung.font_size, family, "start", prefix + entry.abbr
    );
    abbr.setAttribute("data-graha", entry.key);
    if (entry.underline) {
      abbr.setAttribute("text-decoration", "underline");
    }
    cell.appendChild(abbr);
    var degree =
      layout === LAYOUT_STACKED
        ? transitText(
            "transit-deg", rung.x, rung.entries[row].deg_y, rung.font_size,
            family, "start", entry.degree_text
          )
        : transitText(
            "transit-deg", rung.deg_x, rung.rows[row], rung.font_size,
            family, "start", entry.degree_text
          );
    degree.setAttribute("data-graha", entry.key);
    cell.appendChild(degree);
  }

  /* Section 5.3, for one cell: returns what was drawn there. */
  function placeCell(cell, slot, cellEntries, natalBlock) {
    var prefix = natalBlock.prefix;
    var family = natalBlock.font_family;
    var count = cellEntries.length;
    var layout = slot.layout;
    for (var index = 0; index < slot.rungs.length; index++) {
      var rung = slot.rungs[index];
      if (capacityOf(rung, layout) >= count) {
        cellEntries.forEach(function (entry, row) {
          drawEntry(cell, rung, layout, row, entry, prefix, family);
        });
        return { mode: "shown", shown: count, more: 0 };
      }
    }
    var floor = slot.rungs[slot.rungs.length - 1];
    var rows = capacityOf(floor, layout);
    if (rows >= 1) {
      var drawn = rows - 1;
      for (var row = 0; row < drawn; row++) {
        drawEntry(cell, floor, layout, row, cellEntries[row], prefix, family);
      }
      var more = count - drawn;
      var moreY = layout === LAYOUT_STACKED ? floor.overflow_y : floor.rows[drawn];
      cell.appendChild(
        transitText(
          "transit-more", floor.x, moreY, floor.font_size, family, "start",
          `${prefix}+${String(more)}`
        )
      );
      return { mode: "row", shown: drawn, more: more };
    }
    if (slot.marker !== null) {
      cell.appendChild(
        transitText(
          "transit-marker", slot.marker.x, slot.marker.y,
          natalBlock.marker_font_size, family, slot.marker.anchor,
          `${prefix}+${String(count)}`
        )
      );
      return { mode: "marker", shown: 0, more: count };
    }
    return { mode: "panel", shown: 0, more: count };
  }

  function outcomeText(outcome) {
    if (outcome.mode === "shown") {
      return "shown";
    }
    var more = `T:+${String(outcome.more)}`;
    if (outcome.mode === "row") {
      return `${more} in row (${String(outcome.shown)} shown)`;
    }
    if (outcome.mode === "marker") {
      return `${more} marker (0 shown)`;
    }
    return PANEL_ONLY_TEXT;
  }

  function buildGroup(slots, idPrefix, bySign, meta, natalBlock, descText) {
    var group = svgElement("g");
    group.setAttribute("class", "transit");
    group.setAttribute("data-transit-date", meta.date);
    group.setAttribute("data-transit-time", meta.time);
    group.setAttribute("data-transit-zone", meta.zone);
    group.setAttribute("display", "none");
    group.setAttribute("aria-hidden", "true");
    var desc = svgElement("desc");
    desc.setAttribute("id", `${idPrefix}-transit-desc`);
    desc.textContent = descText;
    group.appendChild(desc);
    var outcomes = {};
    SIGN_KEYS.forEach(function (sign) {
      var cellEntries = bySign[sign];
      if (cellEntries.length === 0) {
        return;
      }
      var slot = slots[sign];
      var cell = svgElement("g");
      cell.setAttribute("class", "transit-cell");
      cell.setAttribute("data-rashi", sign);
      cell.setAttribute("data-house", String(slot.house));
      outcomes[sign] = placeCell(cell, slot, cellEntries, natalBlock);
      if (cell.childNodes.length > 0) {
        group.appendChild(cell);
      }
    });
    return { group: group, outcomes: outcomes };
  }

  function planetText(entry, prefix) {
    return `${prefix}${entry.abbr} ${entry.degree_text}${entry.underline ? " ℞" : ""}`;
  }

  /* Builds everything off the document; throws on any fault. Publishes
   * nothing: `commitTransit` does that, only after this has returned. */
  function composeTransit(document_, key) {
    var natalBlock = shown.document.overlay;
    var view = shown.view;
    var entries = document_.overlay.entries;
    var planets = document_.planetary_positions.planets;
    var meta = {
      date: document_.effective.date,
      time: document_.effective.time,
      zone: document_.birth.zone,
      offset: document_.birth.offset
    };
    var bySign = {};
    var signName = {};
    SIGN_KEYS.forEach(function (sign) {
      bySign[sign] = [];
    });
    entries.forEach(function (entry, index) {
      bySign[String(entry.rashi_number)].push(entry);
      signName[String(entry.rashi_number)] = planets[index].sign.name;
    });
    var descParts = entries.map(function (entry, index) {
      var sign = String(entry.rashi_number);
      return (
        `${entry.abbr} ${entry.degree_text}${entry.underline ? " retrograde" : ""} ` +
        `in ${planets[index].sign.name} ` +
        `(house ${String(natalBlock.slots.north[sign].house)})`
      );
    });
    var descText =
      `Transit placements for ${meta.date} ${meta.time} ${meta.zone}: ` +
      `${descParts.join("; ")}.`;

    var fragment = document.createDocumentFragment();
    var north = null;
    var south = null;
    if (view.northRoot) {
      north = buildGroup(
        natalBlock.slots.north, NORTH_PREFIX, bySign, meta, natalBlock, descText
      );
      fragment.appendChild(north.group);
    }
    if (view.southState === SOUTH_PRESENT && view.southRoot) {
      if (composeFault !== null && composeFault() === "south") {
        throw new Error("injected composition fault while building the South Indian group");
      }
      south = buildGroup(
        natalBlock.slots.south, SOUTH_PREFIX, bySign, meta, natalBlock, descText
      );
      fragment.appendChild(south.group);
    }

    if (composeFault !== null && composeFault() === "panel") {
      throw new Error("injected composition fault while building the panel");
    }
    var rows = document.createDocumentFragment();
    var panelRows = [];
    var panelOnly = false;
    SIGN_NUMBERS.forEach(function (house) {
      SIGN_KEYS.forEach(function (sign) {
        if (natalBlock.slots.north[sign].house !== house || bySign[sign].length === 0) {
          return;
        }
        var northText = north ? outcomeText(north.outcomes[sign]) : "North Indian chart not available";
        var southText = south ? outcomeText(south.outcomes[sign]) : TRANSIT_UNAVAILABLE_SOUTH;
        if (northText === PANEL_ONLY_TEXT || southText === PANEL_ONLY_TEXT) {
          panelOnly = true;
        }
        var cells = [
          String(house),
          signName[sign],
          bySign[sign]
            .map(function (entry) {
              return planetText(entry, natalBlock.prefix);
            })
            .join(", "),
          northText,
          southText
        ];
        var tr = element("tr", "v-transit-panel-row");
        tr.setAttribute("data-rashi", sign);
        cells.forEach(function (text) {
          tr.appendChild(element("td", "v-transit-panel-cell", text));
        });
        rows.appendChild(tr);
        panelRows.push(cells);
      });
    });

    var instant = transitInstantText(meta);
    var suffix = panelOnly ? ` ${PANEL_ONLY_SENTENCE}` : "";
    return {
      key: key,
      planets: planets,
      entries: entries,
      offset: meta.offset,
      fragment: fragment,
      groups: { north: north ? north.group : null, south: south ? south.group : null },
      rows: rows,
      panelRows: panelRows,
      summary: `Transits — ${instant} at ${shown.document.effective.place.label}`,
      statusText: `Transits for ${instant} shown.${suffix}`,
      repeatText: `Transits for ${instant} already shown.${suffix}`
    };
  }

  function setGroupShown(group, idPrefix, visible) {
    if (!group || !group.parentNode) {
      return;
    }
    var root = group.parentNode;
    /* `display="none"` stops the painting; `aria-hidden` is set with it
     * because Chromium keeps the texts of an SVG group hidden by `display`
     * in its accessibility tree under the chart image (measured by the
     * acceptance check transit_preserved_state). Both are attributes of the
     * transit group, never of a natal node. */
    if (visible) {
      group.removeAttribute("display");
      group.removeAttribute("aria-hidden");
      root.setAttribute("aria-describedby", `${idPrefix}-desc ${idPrefix}-transit-desc`);
    } else {
      group.setAttribute("display", "none");
      group.setAttribute("aria-hidden", "true");
      root.setAttribute("aria-describedby", `${idPrefix}-desc`);
    }
  }

  function setPanelShown(view, visible) {
    if (!view || !view.transitPanel) {
      return;
    }
    view.transitPanel.hidden = !visible;
    [view.chartHeading, view.southHeading].forEach(function (heading) {
      if (!heading) {
        return;
      }
      if (visible) {
        heading.setAttribute("aria-describedby", "transit-summary");
      } else {
        heading.removeAttribute("aria-describedby");
      }
    });
  }

  function showOverlay(result) {
    setGroupShown(result.groups.north, NORTH_PREFIX, true);
    setGroupShown(result.groups.south, SOUTH_PREFIX, true);
    if (shown && panelHidden(shown.view)) {
      setPanelShown(shown.view, true);
      refreshScrollHints(shown.view);
    }
  }

  function panelHidden(view) {
    return Boolean(view && view.transitPanel && view.transitPanel.hidden);
  }

  function hideOverlay() {
    if (transitResult !== null) {
      setGroupShown(transitResult.groups.north, NORTH_PREFIX, false);
      setGroupShown(transitResult.groups.south, SOUTH_PREFIX, false);
    }
    if (shown && !panelHidden(shown.view)) {
      setPanelShown(shown.view, false);
      refreshScrollHints(shown.view);
    }
  }

  /* Section 6.5's commit, one synchronous sequence. */
  function commitTransit(built) {
    var view = shown.view;
    if (transitResult !== null) {
      [
        [transitResult.groups.north, NORTH_PREFIX],
        [transitResult.groups.south, SOUTH_PREFIX]
      ].forEach(function (pair) {
        var group = pair[0];
        if (group && group.parentNode) {
          var root = group.parentNode;
          root.removeChild(group);
          root.setAttribute("aria-describedby", `${pair[1]}-desc`);
        }
      });
    }
    if (built.groups.north) {
      view.northRoot.appendChild(built.groups.north);
    }
    if (built.groups.south) {
      view.southRoot.appendChild(built.groups.south);
    }
    clear(view.transitBody);
    view.transitBody.appendChild(built.rows);
    setText(view.transitSummary, built.summary);
    transitResult = {
      key: built.key,
      planets: built.planets,
      entries: built.entries,
      offset: built.offset,
      groups: built.groups,
      panelRows: built.panelRows,
      statusText: built.statusText,
      repeatText: built.repeatText
    };
  }

  /* --- section 6.3: the request ----------------------------------------- */

  function recordFailure(key, kind, message, statusText) {
    transitFailure = {
      key: key,
      kind: kind,
      message: message,
      statusText: statusText
    };
    setTransitStatus(statusText, true);
  }

  function errorStatus(document_) {
    var error = document_ && document_.error ? document_.error : null;
    var kind = error && error.kind ? error.kind : "unexpected";
    var message = error && error.message ? error.message : "No message.";
    if (kind === "stale_schema") {
      return { kind: kind, message: message, text: STALE_SCHEMA_SENTENCE };
    }
    if (kind === "input") {
      return { kind: kind, message: message, text: `Transit time not accepted: ${message}` };
    }
    if (kind === "dasha_range") {
      return {
        kind: kind,
        message: message,
        text: `The server could not calculate a chart for this transit date: ${message}`
      };
    }
    return { kind: kind, message: message, text: `Transits could not be calculated: ${message}` };
  }

  /* The owned response, after the ownership guard: items 2 to 8. Every
   * failure of items 6 to 8 is reported here, for this request. */
  function acceptTransit(pending, answer) {
    var key = pending.key;
    if (
      key.natal !== shown ||
      transitDateField.value !== key.date ||
      transitTimeField.value !== key.time ||
      !natalUsable() ||
      !transitOn
    ) {
      return;
    }
    try {
      if (answer.body === null) {
        var notJson = "the server's answer was not the JSON document this page expects.";
        recordFailure(key, "unexpected", notJson, `Transits could not be calculated: ${notJson}`);
        return;
      }
      if (!answer.ok) {
        var failed = errorStatus(answer.body);
        recordFailure(key, failed.kind, failed.message, failed.text);
        return;
      }
      var document_ = answer.body;
      if (!echoMatches(document_, pending.captured)) {
        var echo =
          "the server echoed a different submission than the one this page sent.";
        recordFailure(key, "echo", echo, `Transits could not be calculated: ${echo}`);
        return;
      }
      if (
        !isObject(document_.effective) ||
        document_.effective.time_assumed !== false ||
        document_.effective.source !== "selected"
      ) {
        var assumed = "the server assumed a value this page sent explicitly.";
        recordFailure(key, "assumed", assumed, `Transits could not be calculated: ${assumed}`);
        return;
      }
      var problem = transitOverlayProblem(document_, shown.document.overlay);
      if (problem !== null) {
        recordFailure(
          key,
          "metadata",
          problem,
          "Transits could not be calculated: the server's placement data was " +
            `not usable (${problem})`
        );
        return;
      }
      var built;
      try {
        built = composeTransit(document_, key);
      } catch (error) {
        var reason = error && error.message ? error.message : String(error);
        recordFailure(
          key,
          "composition",
          reason,
          `Transit overlay could not be composed: ${reason}`
        );
        return;
      }
      commitTransit(built);
      transitFailure = null;
      setTransitStatus(built.statusText, true);
    } catch (unexpected) {
      var text = unexpected && unexpected.message ? unexpected.message : String(unexpected);
      recordFailure(key, "unexpected", text, `Transits could not be calculated: ${text}`);
    }
  }

  function requestTransit(key) {
    invalidatePending();
    var captured = {
      date: key.date,
      time: key.time,
      place_text: shown.document.effective.place.label,
      place_id: String(shown.document.effective.place.geoname_id)
    };
    transitSequence = transitSequence + 1;
    var mine = transitSequence;
    var controller = new AbortController();
    transitPending = {
      key: key,
      captured: captured,
      sequence: mine,
      controller: controller
    };
    enterTransitBusy();

    fetch("/api/chart", {
      method: "POST",
      mode: "same-origin",
      credentials: "omit",
      cache: "no-store",
      redirect: "error",
      referrerPolicy: "no-referrer",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "X-Viewer-Token": token
      },
      body: JSON.stringify(captured)
    })
      .then(function (response) {
        return response.json().then(
          function (document_) {
            return { status: response.status, ok: response.ok, body: document_ };
          },
          function () {
            return { status: response.status, ok: false, body: null };
          }
        );
      })
      .then(function (answer) {
        if (!owns(mine)) {
          return;
        }
        var pending = transitPending;
        transitPending = null;
        acceptTransit(pending, answer);
        leaveTransitBusy();
        syncOverlay();
      })
      .catch(function (error) {
        if (!owns(mine)) {
          return;
        }
        var pending = transitPending;
        transitPending = null;
        if (pending.key.natal === shown && transitOn) {
          var reason = `the viewer could not reach its own server: ${String(error)}`;
          recordFailure(
            pending.key,
            "network",
            reason,
            `Transits could not be calculated: ${reason}`
          );
        }
        leaveTransitBusy();
        syncOverlay();
      });
  }

  /* Rules (a) and (b) of section 3.3, and the duplicate and retry rules. */
  function considerRequest(isUpdate) {
    if (!natalUsable()) {
      setTransitStatus(restingStatus(false), true);
      return;
    }
    if (!inputsComplete()) {
      setTransitStatus(INCOMPLETE_TRANSIT, true);
      return;
    }
    var key = currentKey();
    if (transitPending && sameKey(transitPending.key, key)) {
      setTransitStatus(CALCULATING_TRANSITS, true);
      return;
    }
    var matches = transitResult !== null && sameKey(transitResult.key, key);
    var failedHere = transitFailure !== null && sameKey(transitFailure.key, key);
    if (matches && !failedHere) {
      setTransitStatus(isUpdate ? transitResult.repeatText : transitResult.statusText, true);
      return;
    }
    requestTransit(key);
  }

  function onTransitToggle() {
    transitOn = transitToggle.checked;
    if (transitOn) {
      considerRequest(false);
    } else {
      invalidatePending();
      setTransitStatus(TRANSITS_OFF, true);
    }
    syncOverlay();
  }

  function onTransitUpdate() {
    if (!transitOn) {
      setTransitStatus("Turn on Show transits to see transits.", true);
    } else {
      considerRequest(true);
    }
    syncOverlay();
  }

  function onTransitInput() {
    invalidatePending();
    if (transitOn) {
      setTransitStatus(restingStatus(true), true);
    }
    syncOverlay();
  }

  function onTransitKeydown(event) {
    if (event.key !== "Enter") {
      return;
    }
    if (event.target !== transitDateField && event.target !== transitTimeField) {
      return;
    }
    event.preventDefault();
    onTransitUpdate();
  }

  /* Section 3.4: a fieldset that becomes disabled while it holds focus hands
   * it to the checked chart-style radio, as Layer 19 does for a hidden block. */
  function setTransitEnabled(enabled) {
    var active = document.activeElement;
    var held = !enabled && active !== null && transitGroup.contains(active);
    transitGroup.disabled = !enabled;
    if (held) {
      styleInputs.forEach(function (input) {
        if (input && input.checked) {
          input.focus();
        }
      });
    }
  }

  /* The natal document has just replaced the results (section 6.4). */
  function onNatalApplied(document_) {
    natalLoading = false;
    invalidatePending();
    transitResult = null;
    transitFailure = null;
    var problem = natalOverlayProblem(document_);
    if (problem === null) {
      overlayMeta = META_OK;
      overlayProblem = "";
    } else {
      overlayMeta = document_.overlay === undefined ? META_MISSING : META_MALFORMED;
      overlayProblem = problem;
    }
    var place = document_.effective && document_.effective.place;
    var zone = document_.location ? document_.location.timezone_id : "";
    setText(
      transitPlace,
      place ? `Local time at ${place.label} — ${zone} (the natal birthplace)` : ""
    );
    if (overlayMeta === META_OK) {
      setTransitEnabled(true);
      setTransitStatus(transitOn ? NEW_NATAL_TRANSIT : "", false);
      return;
    }
    transitToggle.checked = false;
    transitOn = false;
    setTransitEnabled(false);
    setTransitStatus(
      "Transit overlay not available: the server did not provide usable " +
        `placement data (${overlayProblem}). Reload the page or restart the viewer.`,
      false
    );
  }

  /* The natal form went stale or came back (section 6.4). */
  function onNatalStale(wasStale, isStale) {
    if (isStale) {
      invalidatePending();
    }
    if (transitOn && overlayMeta === META_OK && wasStale !== isStale) {
      setTransitStatus(isStale ? NATAL_STALE_TRANSIT : restingStatus(false), false);
    }
    syncOverlay();
  }

  /* Section 3.1: unchecked, blank and disabled until a document with usable
   * metadata arrives, whatever the browser may restore into the controls. */
  function wireTransitControl() {
    transitToggle.checked = false;
    transitOn = false;
    transitDateField.value = "";
    transitTimeField.value = "";
    transitGroup.disabled = true;
    transitToggle.addEventListener("change", onTransitToggle);
    transitUpdate.addEventListener("click", onTransitUpdate);
    transitDateField.addEventListener("input", onTransitInput);
    transitTimeField.addEventListener("input", onTransitInput);
    transitGroup.addEventListener("keydown", onTransitKeydown);
  }

  /* --- wiring --------------------------------------------------------- */

  fillDefaultPlaceText();
  wireCombobox();
  wireStyleControl();
  wireTransitControl();

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    submit();
  });

  cancelButton.addEventListener("click", function () {
    if (inFlight) {
      cancelledSequence = sequence;
      inFlight.abort();
    }
  });

  [dateField, timeField].forEach(function (field) {
    field.addEventListener("input", refreshStale);
  });

  window.addEventListener("resize", function () {
    if (shown) {
      refreshScrollHints(shown.view);
    }
  });

  /* The one test seam (Layer 14 section 13.4): present only when the page was
   * opened with #acceptance, so the ordinary page has no way to bypass the
   * server. It takes one schema `vedic_chart.viewer/2` document. */
  if (window.location.hash === "#acceptance") {
    window.__loadFixture = function (transported) {
      applyDocument(transported);
      return true;
    };
    /* Layer 20 section 10.8: the composition fault seam, on the same terms.
     * A metadata-valid response cannot make composition fail, so the
     * acceptance script sets `window.__transitComposeFault` to "south" or
     * "panel"; `composeTransit` -- and nothing else -- consults it, after the
     * response has been validated, and throws at the start of building the
     * South Indian group or the panel rows. Without #acceptance this hook is
     * never installed and the property is never read. */
    composeFault = function () {
      return window.__transitComposeFault;
    };
  }
})();
