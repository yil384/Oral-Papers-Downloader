class PaperBrowser {
  constructor() {
    this.papers = [];
    this.filteredPapers = [];
    this.currentFilters = {
      conferences: new Set(),
      years: new Set(),
    };
    this.availableConferences = new Set();
    this.availableYears = new Set();
    this.currentPaper = null;

    this.initializeEventListeners();
    this.loadPapers();
  }

  initializeEventListeners() {
    // Search functionality
    document.getElementById("searchInput").addEventListener("input", (e) => {
      this.filterPapers(e.target.value);
    });

    document.getElementById("searchButton").addEventListener("click", () => {
      const query = document.getElementById("searchInput").value;
      this.filterPapers(query);
    });
  }

  async loadPapers() {
    try {
      // Define all possible conference data sources
      const dataSources = [
        {
          name: "NeurIPS 2023",
          path: "neurips_2023_papers/metadata/downloaded_papers.json",
          conference: "NeurIPS",
          year: 2023,
        },
        {
          name: "NeurIPS 2024",
          path: "neurips_2024_papers/metadata/downloaded_papers.json",
          conference: "NeurIPS",
          year: 2024,
        },
        {
          name: "ICLR 2024",
          path: "iclr_2024_papers/metadata/downloaded_papers.json",
          conference: "ICLR",
          year: 2024,
        },
        {
          name: "ICML 2025",
          path: "icml_2025_papers/metadata/downloaded_papers.json",
          conference: "ICML",
          year: 2025,
        },
        {
          name: "CVPR 2024",
          path: "cvpr_2024_papers/metadata/downloaded_papers.json",
          conference: "CVPR",
          year: 2024,
          format: "cvpr",
        },
        {
          name: "CVPR 2025",
          path: "cvpr_2025_papers/metadata/downloaded_papers.json",
          conference: "CVPR",
          year: 2025,
          format: "cvpr",
        },
      ];

      let loadedPapers = [];

      for (const source of dataSources) {
        try {
          const response = await fetch(source.path);
          if (response.ok) {
            let papers = await response.json();

            // Handle CVPR special format
            if (source.format === "cvpr") {
              papers = papers.map((paper) =>
                this.convertCVPRFormat(paper, source.conference, source.year)
              );
            } else {
              // Add conference and year info to standard format
              papers = papers.map((paper) => ({
                ...paper,
                conference: source.conference,
                year: source.year,
              }));
            }

            loadedPapers = loadedPapers.concat(papers);
            console.log(
              `Successfully loaded ${source.name}: ${papers.length} papers`
            );
          }
        } catch (error) {
          console.log(`Failed to load ${source.path}: ${error.message}`);
        }
      }

      if (loadedPapers.length === 0) {
        this.showError(
          "Unable to load any paper data. Please check file paths."
        );
        return;
      }

      this.papers = loadedPapers;
      this.updateAvailableFilters();
      this.renderFilterTags();
      this.filterPapers();
      this.updateStats();
    } catch (error) {
      console.error("Failed to load paper data:", error);
      this.showError("Error loading paper data: " + error.message);
    }
  }

  // Convert CVPR format to standard format
  convertCVPRFormat(paper, conference, year) {
    return {
      id: this.generateId(paper.title),
      title: paper.title,
      authors: paper.authors || "Unknown",
      abstract: paper.summary || paper.abstract || "",
      conference: conference,
      year: year,
      pdf_url: paper.pdf_url,
      download_status: "success",
      download_method: "cvpr",
      search_queries: {
        google: `${paper.title} ${conference} ${year} pdf`,
      },
    };
  }

  generateId(title) {
    return title
      .split("")
      .reduce((a, b) => {
        a = (a << 5) - a + b.charCodeAt(0);
        return a & a;
      }, 0)
      .toString();
  }

  updateAvailableFilters() {
    this.availableConferences.clear();
    this.availableYears.clear();

    this.papers.forEach((paper) => {
      if (paper.conference) {
        this.availableConferences.add(paper.conference);
      }
      if (paper.year) {
        this.availableYears.add(paper.year);
      }
    });
  }

  renderFilterTags() {
    this.renderConferenceFilters();
    this.renderYearFilters();
  }

  renderConferenceFilters() {
    const container = document.getElementById("conferenceFilters");
    const conferences = Array.from(this.availableConferences).sort();

    container.innerHTML = conferences
      .map(
        (conf) => `
            <span class="filter-tag" data-type="conference" data-value="${conf}">
                ${conf}
            </span>
        `
      )
      .join("");

    // Add click events
    container.querySelectorAll(".filter-tag").forEach((tag) => {
      tag.addEventListener("click", (e) => {
        const type = e.target.getAttribute("data-type");
        const value = e.target.getAttribute("data-value");
        this.toggleFilter(type, value, e.target);
      });
    });
  }

  renderYearFilters() {
    const container = document.getElementById("yearFilters");
    const years = Array.from(this.availableYears).sort((a, b) => b - a); // Descending order

    container.innerHTML = years
      .map(
        (year) => `
            <span class="filter-tag" data-type="year" data-value="${year}">
                ${year}
            </span>
        `
      )
      .join("");

    // Add click events
    container.querySelectorAll(".filter-tag").forEach((tag) => {
      tag.addEventListener("click", (e) => {
        const type = e.target.getAttribute("data-type");
        const value = e.target.getAttribute("data-value");
        this.toggleFilter(type, value, e.target);
      });
    });
  }

  toggleFilter(type, value, element) {
    element.classList.toggle("active");

    const filterSet = this.currentFilters[type + "s"];
    if (element.classList.contains("active")) {
      filterSet.add(value);
    } else {
      filterSet.delete(value);
    }

    this.filterPapers(document.getElementById("searchInput").value);
  }

  filterPapers(query = "") {
    const searchTerm = query.toLowerCase().trim();

    this.filteredPapers = this.papers.filter((paper) => {
      // Conference filter
      if (
        this.currentFilters.conferences.size > 0 &&
        !this.currentFilters.conferences.has(paper.conference)
      ) {
        return false;
      }

      // Year filter - FIXED: convert to string for comparison
      if (this.currentFilters.years.size > 0) {
        const paperYear = paper.year.toString();
        const selectedYears = Array.from(this.currentFilters.years).map((y) =>
          y.toString()
        );
        if (!selectedYears.includes(paperYear)) {
          return false;
        }
      }

      // Search filter
      if (searchTerm) {
        const inTitle = paper.title.toLowerCase().includes(searchTerm);
        const inAuthors = paper.authors.toLowerCase().includes(searchTerm);
        const inAbstract = paper.abstract
          ? paper.abstract.toLowerCase().includes(searchTerm)
          : false;

        return inTitle || inAuthors || inAbstract;
      }

      return true;
    });

    this.renderPaperList();
    this.updateStats();
  }

  renderPaperList() {
    const container = document.getElementById("paperList");

    if (this.filteredPapers.length === 0) {
      container.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="fas fa-search fa-2x mb-2"></i>
                    <p>No matching papers found</p>
                    <small>Try adjusting your search terms or filters</small>
                </div>
            `;
      return;
    }

    container.innerHTML = this.filteredPapers
      .map(
        (paper) => `
            <div class="paper-item ${
              this.currentPaper && this.currentPaper.id === paper.id
                ? "active"
                : ""
            }" 
                 data-paper-id="${paper.id}">
                <div class="paper-title">${this.truncateText(
                  paper.title,
                  70
                )}</div>
                <div class="paper-authors">${this.truncateText(
                  paper.authors,
                  50
                )}</div>
                <div class="paper-tags">
                    <span class="paper-tag conference">${
                      paper.conference
                    }</span>
                    <span class="paper-tag year">${paper.year}</span>
                </div>
            </div>
        `
      )
      .join("");

    // Add click events
    container.querySelectorAll(".paper-item").forEach((item) => {
      item.addEventListener("click", () => {
        const paperId = item.getAttribute("data-paper-id");
        this.selectPaper(paperId);
      });
    });
  }

  selectPaper(paperId) {
    const paper = this.papers.find((p) => p.id === paperId);
    if (!paper) return;

    this.currentPaper = paper;

    // Update active state in list
    document.querySelectorAll(".paper-item").forEach((item) => {
      item.classList.remove("active");
    });
    document
      .querySelector(`[data-paper-id="${paperId}"]`)
      .classList.add("active");

    // Show paper detail (PDF only)
    this.showPaperPDF(paper);
  }

  showPaperPDF(paper) {
    document.getElementById("noSelection").style.display = "none";
    document.getElementById("paperDetail").style.display = "block";

    // Show PDF
    this.showPDF(paper);
  }

  showPDF(paper) {
    const pdfViewer = document.getElementById("pdfViewer");
    let pdfPath = "";

    if (paper.local_pdf_path) {
      // Use local PDF path
      pdfPath = paper.local_pdf_path;
    } else if (paper.pdf_url) {
      // Use online PDF URL
      pdfPath = paper.pdf_url;
    } else {
      // Try to construct default path
      const safeTitle = paper.title
        .replace(/[^a-zA-Z0-9]/g, "_")
        .substring(0, 50);
      pdfPath = `${paper.conference.toLowerCase()}_${paper.year}_papers/pdfs/${
        paper.id
      }_${safeTitle}.pdf`;
    }

    console.log("Loading PDF from:", pdfPath);
    pdfViewer.src = pdfPath;
  }

  updateStats() {
    document.getElementById("totalCount").textContent = this.papers.length;
    document.getElementById("filterCount").textContent =
      this.filteredPapers.length;
    document.getElementById("conferenceCount").textContent =
      this.availableConferences.size;
  }

  truncateText(text, maxLength) {
    if (!text) return "";
    return text.length > maxLength
      ? text.substring(0, maxLength) + "..."
      : text;
  }

  showError(message) {
    const container = document.getElementById("paperList");
    container.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                ${message}
            </div>
        `;
  }
}

// Initialize application
document.addEventListener("DOMContentLoaded", () => {
  new PaperBrowser();
});
