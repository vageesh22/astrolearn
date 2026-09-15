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
    applyScrollHint(view.tableWrapper, view.tableHint);
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
  }

  function leaveLoading() {
    hide(cancelButton);
    resultsRegion.removeAttribute("aria-busy");
    resultsRegion.removeAttribute("data-busy");
    resultsRegion.removeAttribute("inert");
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
    /* Measured now that the subtree is in the document: geometry read off an
     * off-document fragment is meaningless. */
    refreshScrollHints(view);
    refreshStale();

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
      tableWrapper: fragment.querySelector("#table-wrapper"),
      tableHint: fragment.querySelector("#table-scroll-hint"),
      nodesByRow: new Map(),
      idByChain: new Map(),
      abbrByLord: new Map(),
      microseconds: false,
      suspendHints: false
    };

    fillSummary(fragment, document_);
    fillBadges(fragment, document_);
    fillBirthDetails(fragment, document_);
    fillChart(fragment, document_);
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
    ["#results-badge", "#chart-badge", "#dasha-badge"].forEach(function (id) {
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
    if (same) {
      resultsRegion.removeAttribute("data-stale");
      hide(shown.view.stale);
      return;
    }
    resultsRegion.setAttribute("data-stale", "true");
    setText(
      shown.view.stale,
      `Inputs changed — the results below are for ` +
        `${describeSubmitted(submitted)}. Press Generate to recalculate.`
    );
    show(shown.view.stale);
  }

  /* --- wiring --------------------------------------------------------- */

  fillDefaultPlaceText();
  wireCombobox();

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
  }
})();
