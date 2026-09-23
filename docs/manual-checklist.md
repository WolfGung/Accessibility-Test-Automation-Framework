# Manual accessibility checklist

What the automated layers of this repository do not decide. The scan (axe-core) and the keyboard checks report what they can measure; whether a text alternative says the right thing, what a screen reader announces, how a page holds up when it is enlarged, and whether an error message helps are read, listened to and judged by a person. Each item below says how to check and what counts as a failure, with the WCAG 2.1 success criteria it bears on.

The items are written for this shop's pages — the product list, a product page, the cart, the checkout, the "Added to cart" dialog and the confirmation — in both of its modes (`A11Y_MODE=fixed` and `A11Y_MODE=broken`, see the README for how to run either). Two of the ten planted violations are found by no automated layer, and the last two sections are theirs.

For each item, record the page, the mode, the browser and the assistive technology used, and what was observed. A failure is a fact about the page, filed against the criterion it bears on.

## Alt text quality

Success criterion 1.1.1 Non-text Content. The scan finds an image with no `alt` attribute; whether the text says what the picture shows, it cannot tell.

### How to check

1. Open the product list and each product page. For every image, read its text alternative next to the picture: in the browser's developer tools, or with a screen reader (see the next section), or with the images turned off.
2. Ask of each: does the text say what a sighted shopper learns from the picture — colour, shape, material — without repeating the product name that is already printed beside it? (In this shop: "White ceramic mug with a dark blue rim and handle" next to the name "Ceramic mug".)
3. Check the icons: the bin icon inside the cart's remove control is a picture only and carries `aria-hidden="true"`; the control around it carries the name.

### What counts as a failure

- An image whose text alternative is the file name, the product name alone, "image" or "photo", or words unrelated to the picture.
- A picture that conveys something the text leaves out: a colour, a variant, a state.
- A meaningful image marked decorative (`alt=""`), or a decorative one that is announced.
- An icon inside a named control that is read out on top of the control's name.

## Screen readers: NVDA and VoiceOver

Success criteria 1.3.1 Info and Relationships, 2.4.3 Focus Order, 4.1.2 Name, Role, Value, and 4.1.3 Status Messages. Test with NVDA on Windows, in Firefox or Chrome, and with VoiceOver on macOS, in Safari: two readers with different reading models, and a page that works in one does not always work in the other.

### How to check

1. NVDA: start NVDA, open the page in Firefox or Chrome, read from the top with the Down arrow (browse mode), then move through the controls with Tab. Press H to move between headings, F between form fields, B between buttons; open the elements list (NVDA+F7) to see the links, headings and form fields the reader found.
2. VoiceOver: start VoiceOver (Cmd+F5), open the page in Safari, read with VO+Right arrow, then move through the controls with Tab. Open the rotor (VO+U) to list headings, links and form controls.
3. On each page, listen to what is announced for the heading, each product image, each link and button, each field with its label, the cart count and the dialog's title and message. Then do the shopper's steps by keyboard and listen to what each step announces: add a product from the list and from a product page, close the dialog, open the cart, remove a line, submit the checkout empty, place an order.

### What counts as a failure

- A control announced without a role ("clickable", or nothing) or without a name, so the listener cannot tell what it does. The cart's remove control in the broken mode is one; see its own section below.
- A field announced without its label, or with another field's label.
- A heading, a list or the order summary announced as plain text: the structure is not conveyed.
- After an action, nothing says what happened: the dialog opens without its title being read, a line is removed silently, the form comes back with errors and the reader hears nothing of it.
- Focus that lands somewhere other than where the reader says it is, or that moves without the user's action.

## 200% zoom and reflow at 320 CSS px

Success criteria 1.4.4 Resize Text, 1.4.10 Reflow and 1.4.12 Text Spacing.

### How to check

1. In a desktop browser at 1280 px wide, set the zoom to 200% (Ctrl or Cmd and +). Go through every page, open the dialog, and bring the checkout back with errors.
2. Set the zoom to 400% at 1280 px wide, or make the window 320 CSS px wide (the device toolbar of the developer tools does this). Go through every page again, the dialog and the checkout with errors included.
3. Apply the text-spacing values of 1.4.12 with a bookmarklet or a user stylesheet — line height 1.5 times the font size, paragraph spacing 2 times, letter spacing 0.12 times, word spacing 0.16 times — and look again at the cart lines, the dialog and the checkout with errors.

### What counts as a failure

- Text or controls cut off, overlapping or hidden behind another element.
- Scrolling in two directions to read a line of text. (A table or an image wider than the screen may scroll sideways on its own; running text may not.)
- A control that cannot be reached or operated: the dialog's buttons below the bottom of the window with no way to scroll to them, a field whose error text is out of view when the field takes focus.
- Content or function that disappears at the larger size and is not available in another way.

## Error message clarity

Success criteria 3.3.1 Error Identification and 3.3.3 Error Suggestion. The keyboard checks submit valid details, and nothing automated reads a message and judges whether it helps.

### How to check

1. With something in the cart, open the checkout and submit the form empty. Read the summary at the top of the form, the message next to each field, and the page's title in the tab.
2. Enter an email address without an @ and submit. Then choose no country and submit.
3. Read each message on its own, as a screen reader announces it when the field takes focus: does it say which field and what to enter?

In the fixed mode the messages are "Enter your full name", "Enter your email address", "Enter your street address", "Enter your town or city", "Enter your postal code", "Select your country" and "Enter an email address in the correct format, like name@example.com"; each stands on its own, next to its field, as a link in the summary and in the reader's announcement of the field.

### What counts as a failure

- A message that says only that something is wrong ("Invalid", "Error", "Required") and not what to enter.
- A message not tied to its field — the reader announces the field without it — or missing from the summary.
- An error shown only as a colour, an icon or a border.
- A message that names the field by a word the form does not show, or that blames the user.
- A title that does not change when errors are shown, so a reader that announces the title when the page loads says nothing of them.

## `error-identification`: checkout errors are shown only as a red border

Success criterion 3.3.1 Error Identification. Page: the checkout, after a submit with errors, in the broken mode. Neither the scan nor the keyboard checks report it — a coloured border is valid markup, and no check reads error text — so it is found by hand.

### How to check

1. Run the shop in the broken mode, put a product in the cart, open the checkout and submit it empty.
2. Look at the page: which fields are marked, and how? Is there any text saying what is wrong? Read the title in the tab.
3. With NVDA or VoiceOver, Tab to each field and listen to what is announced with it.
4. Do the same in the fixed mode and compare.

### What counts as a failure

- The only sign of an error is the colour of a field's border: no text saying which field is wrong and what to enter, no summary, no change of title.
- A field in error is not announced as invalid, and no message is read with it.

For comparison, the fixed mode shows each field in error with the text "Error: …" above it, marks the field with `aria-invalid="true"` and `aria-describedby` pointing at that text, puts focus on a summary headed "There is a problem" with a link to each field, and starts the title with "Error:".

## `div-button`: the cart's remove control has no role and no name

Success criterion 4.1.2 Name, Role, Value. Page: the cart, in the broken mode. The keyboard checks reach the control and can operate it — it takes focus, answers Enter and Space and keeps the focus outline — so they report nothing; what it lacks is heard only through a screen reader.

### How to check

1. Run the shop in the broken mode, add a product, open the cart.
2. With NVDA or VoiceOver, Tab to the control after the line's subtotal and listen to what is announced. Then open the reader's list of buttons or form controls and look for it.
3. Do the same in the fixed mode and compare.

### What counts as a failure

- The control is announced without a role (not as a button) or without a name — nothing, "clickable", or the icon's markup — or it is absent from the reader's list of controls.
- Activating it with the reader's own command (NVDA: Enter or Space in focus mode; VoiceOver: VO+Space) does nothing.

For comparison, the fixed mode's control is a `button` named "Remove" followed by the product's name, with the icon hidden from assistive technology by `aria-hidden="true"`.
