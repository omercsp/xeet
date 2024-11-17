# Features

* Tests organization, configuration, and orchestration tool:
  - CLI
  - RESTful server
  - CI/CD integrations
  - Web server
  - Container?
  - Cloud image?

* Can handle anything runnable as a test. It isn’t limited to API, Web, CLI, DB, etc. Can also mix
  and match different types of runs and verifications (e.g., run an API test and check the DB as the
  verification step).

* Tests are based on running an executable, not on using a specific library (e.g., Selenium) or
  specific language (e.g., JS). Verification might be based on the program RC and output, but the
  internals might do anything (e.g., verify a DB record or so) and output accordingly. This
  separation allows Xeet to run anything, unlike other platforms, which are contained in a
  technology/language boundary.

* Pluggable test steps components (pre-run, test, verification, post-run). Will include some
  out-of-the-box preliminary plugins for simple steps, like:
  - Binary running
  - REST API calling
  - HTTP status validation
  - JSON value(s) validation
  - RC verification
  - Output verification
  - etc.

* Allows users to use Xeet to test anything they want:
  - Using dedicated plugins if suitable (should be for many cases)
  - Through running their own binary with the included binary plugin
  - By developing their own test/verify plugin

---

# General Points

* There doesn’t seem to be any “generic” testing framework. Most tools are dedicated to API or E2E
  (modern code name for web applications, as if there aren’t any other types). Some tools allow both
  API and Web tests together.
* Existing tests written in Selenium.
* There doesn’t seem to be any CLI testing framework at all. One can utilize something like
  [task](https://github.com/go-task/task), which isn’t purposed for testing.
* Many tools have many features hard to replicate. Integration with popular tools seems more
  beneficial than re-creating them.
* No-code solutions seem to be lacking.

---

# Opportunities

* Tests/Verifications not covered by current frameworks (e.g., CLI, DB, etc.)
* Projects requiring multiple testing suits (easier integration, report, orchestration, etc.)
* Projects with un-orchestrated tests (e.g., tests written in Selenium that need to be managed)
* Projects that require complicated tests that are hard to maintain using existing tools
* Projects in transition from one framework to another

---

# Tools

## Testim.io

* [Testim.io](https://www.testim.io/)
* Paid service.
* Used for web E2E testing. It has a very rich UI and features. If the entire application is
  web-based, it is enough by itself to test (not likely though, as very few applications don’t have
  backends with API, etc.).
* Declares that it can import Selenium tests; seems that this isn’t a very smooth import as it
  requires translation to the Testim.io framework.
* In general, a no-code service, at least for simple cases.
* Has API (implies possible dedicated plugin).

## [Katalon Studio](https://katalon.com/)

* ([Privately held, Series A, 250-500 employees](https://www.crunchbase.com/organization/katalon)).
* Focuses on no-code, like Testim.io.
* Has coding features (JS).
* Tests E2E and API, supports Mobile and Desktop as well.
* Includes orchestration.

## [Cypress](https://www.cypress.io/)

* ([Privately held, Series B](https://www.crunchbase.com/organization/cypress-io)).
* E2E testing
* Requires coding (JS)
* Has a recording ability but requires coding in general

## [Selenium](https://www.selenium.dev/)

* Open-source library.
* Requires coding (has bindings to multiple languages).
* Used for E2E testing

## [Playwright](https://playwright.dev/)

* Open-source library.
* E2E testing
* Node.js-based.
* Has some recording ability but requires coding in general.

## [Puppeteer](https://pptr.dev/)

* Open-source library.
* Requires coding (has bindings to multiple languages).
* Used for E2E testing

## [Rainforest QA](https://www.rainforestqa.com/)

* Paid service.
* E2E testing (web)
* Record and playback
* On site compared to Playwright

## [Postman](https://www.postman.com/)

* Free/Paid application.
  - Paid versions include premium options like mock requests.

## [TestProject](https://testproject.io/)

* Open-source
* Can be used to write both API and E2E tests
* Requires coding (JS)

## [TestCafe](https://testcafe.io/)

* Open-source.
* E2E testing
* Requires coding (JS)

## [Robot Framework](https://robotframework.org/)

* Theoretically can test anything.
* Uses native language binding.
  - Restricted to supported libraries.
  - Limited to what the library exposes as a command.
* Existing for a long time but doesn’t seem to gain momentum. Not very popular.

---

# Test Management Tools

* Testrail
* Testiny
* [Qase.io](https://qase.io/)


# Unsorted
* Lambdatest
* Testigma
* SourceLabs
* Zephyr (test management?)
* Xray (test management?)
* BrowserStack
