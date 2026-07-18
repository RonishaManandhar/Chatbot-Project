/*
 * Sidebar menu for Bootstrap 4.
 * Handles desktop collapse, mobile drawer behaviour and nested menu state.
 */
(function ($) {
    "use strict";

    const wrapper = $("#wrapper");
    const sidebarToggle = $("#sidebar-toggle");

    function isMobile() {
        return window.matchMedia("(max-width: 767.98px)").matches;
    }

    function updateToggleAccessibility() {
        const isOpen = isMobile()
            ? wrapper.hasClass("sidebar-toggle")
            : !wrapper.hasClass("sidebar-toggle");

        sidebarToggle.attr("aria-expanded", String(isOpen));
    }

    sidebarToggle.on("click", function (event) {
        event.preventDefault();
        wrapper.toggleClass("sidebar-toggle");
        updateToggleAccessibility();
    });

    $(document).on("click", function (event) {
        if (!isMobile() || !wrapper.hasClass("sidebar-toggle")) {
            return;
        }

        const target = $(event.target);
        const clickedSidebar = target.closest(".sidebar").length > 0;
        const clickedToggle = target.closest("#sidebar-toggle").length > 0;

        if (!clickedSidebar && !clickedToggle) {
            wrapper.removeClass("sidebar-toggle");
            updateToggleAccessibility();
        }
    });

    $(window).on("resize", function () {
        updateToggleAccessibility();
    });

    $(".link-current").each(function () {
        const currentLink = $(this);

        if (currentLink.hasClass("link-arrow")) {
            currentLink.addClass("active down");
            currentLink.next(".list-hidden").show();
        }
    });

    $(".link-arrow").on("click", function (event) {
        event.preventDefault();

        const link = $(this);
        const submenu = link.next(".list-hidden");

        link.toggleClass("active rotate");
        submenu.stop(true, true).slideToggle("fast");
    });

    updateToggleAccessibility();
})(jQuery);
